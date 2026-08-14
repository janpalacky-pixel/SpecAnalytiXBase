# src/modules/data_analysis/spectral_calculator_manager.py

import ast
import operator
import uuid
import numpy as np
from datetime import datetime
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match
from src.modules.utils.correction_history import append_correction_history

logger = get_logger(__name__)


class FormulaSecurityError(ValueError):
    """Raised when a formula contains constructs outside the allowed
    whitelist (attribute access, imports, comprehensions, string/byte
    literals, etc). A ValueError subclass so existing callers that catch
    ValueError for "bad formula" still work without changes."""
    pass


class _SafeFormulaEvaluator:
    """Evaluates a restricted arithmetic expression AST without ever
    calling eval()/exec()/compile() on the formula, and without ever
    performing attribute access (`.`) on anything.

    WHY NOT eval() WITH A STRIPPED __builtins__:
    That pattern (`eval(formula, {"__builtins__": {}}, namespace)`) is a
    famous, well-documented sandbox escape, not a real sandbox. Blocking
    __builtins__ only blocks the NAME "import"/"open"/"exec" etc. from
    being looked up directly. It does nothing to stop attribute access on
    any object already reachable from the namespace — and every ordinary
    Python object (including every numpy array a spectrum's y_scale
    already puts in this namespace) exposes a chain like
    `x.__class__.__base__.__subclasses__()` that walks back to every
    loaded class, including ones that hand back a working `__import__`.
    From there the formula box has the same power as a Python shell:
    reading/writing arbitrary files, running arbitrary shell commands,
    etc. This was verified directly against the previous version of this
    file (not a theoretical concern): a formula using exactly that chain
    executed an arbitrary shell command as the application's own user.

    THE FIX: never call eval() on the expression at all. Parse it to an
    AST (ast.parse — this only builds a syntax tree, it does not execute
    anything) and walk that tree by hand, evaluating ONLY the node types
    explicitly whitelisted below. In particular, ast.Attribute (`.`) is
    never in that whitelist, so there is no way for a formula to reach
    `__class__` or any other dunder — the entire escape chain requires
    attribute access as its first step, and that step doesn't exist here.
    """

    _BIN_OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
    }
    _UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}

    # Formulas are short mathematical expressions, not programs — a cap
    # on node count is cheap insurance against a pathological formula
    # (e.g. deeply nested exponentiation of huge integer literals) being
    # used to hang or exhaust memory rather than to escape the sandbox.
    _MAX_NODES = 400
    _MAX_LITERAL_MAGNITUDE = 1e15

    def __init__(self, names: dict, functions: dict, constants: dict):
        self.names = names          # spectrum variable name -> ndarray
        self.functions = functions  # function name -> callable
        self.constants = constants  # bare-name constant -> float (pi, e)

    def evaluate(self, formula: str):
        try:
            tree = ast.parse(formula, mode='eval')
        except SyntaxError as exc:
            raise ValueError(f"Formula syntax error: {exc}") from exc

        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > self._MAX_NODES:
            raise FormulaSecurityError(
                f"Formula is too complex ({node_count} elements, limit "
                f"{self._MAX_NODES}). Simplify it or split it into fewer steps."
            )

        return self._eval(tree.body)

    def _eval(self, node):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise FormulaSecurityError(
                    "Only numbers are allowed as literals in a formula "
                    "(text, bytes, and boolean/None literals are not)."
                )
            if abs(node.value) > self._MAX_LITERAL_MAGNITUDE:
                raise FormulaSecurityError(
                    f"Numeric literal {node.value!r} is unreasonably large "
                    f"for a formula."
                )
            return node.value

        if isinstance(node, ast.Name):
            if node.id in self.names:
                return self.names[node.id]
            if node.id in self.constants:
                return self.constants[node.id]
            raise ValueError(
                f"Unknown name '{node.id}' in formula — not a selected "
                f"spectrum alias or a recognised constant."
            )

        if isinstance(node, ast.BinOp):
            op = self._BIN_OPS.get(type(node.op))
            if op is None:
                raise FormulaSecurityError(
                    f"Operator '{type(node.op).__name__}' is not allowed in formulas."
                )
            return op(self._eval(node.left), self._eval(node.right))

        if isinstance(node, ast.UnaryOp):
            op = self._UNARY_OPS.get(type(node.op))
            if op is None:
                raise FormulaSecurityError(
                    f"Unary operator '{type(node.op).__name__}' is not allowed in formulas."
                )
            return op(self._eval(node.operand))

        if isinstance(node, ast.Call):
            # Deliberately requires node.func to be a plain ast.Name — a
            # call like `sp1.something()` would have node.func be an
            # ast.Attribute instead, which falls through to the catch-all
            # rejection below. Only a bare, whitelisted function name can
            # ever be called; there is no path to calling a METHOD on
            # anything.
            if not isinstance(node.func, ast.Name) or node.func.id not in self.functions:
                bad = node.func.id if isinstance(node.func, ast.Name) else '<expression>'
                raise ValueError(
                    f"Unknown function '{bad}' in formula. See the function "
                    f"reference panel for the available functions."
                )
            if node.keywords:
                raise FormulaSecurityError(
                    "Keyword arguments are not allowed in formula function calls."
                )
            args = [self._eval(a) for a in node.args]
            try:
                return self.functions[node.func.id](*args)
            except FormulaSecurityError:
                raise
            except Exception as exc:
                raise ValueError(f"{node.func.id}(): {exc}") from exc

        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._eval(elt) for elt in node.elts]

        # Explicit rejection covers ast.Attribute, ast.Subscript,
        # ast.Lambda, ast.comprehension/ListComp/SetComp/GeneratorExp,
        # ast.Dict, ast.Set, ast.Str/ast.Bytes (pre-3.8), ast.Starred,
        # ast.Compare, ast.BoolOp, f-strings, walrus, and anything else
        # not explicitly handled above — i.e. everything that isn't pure
        # arithmetic over numbers, spectra, and whitelisted function calls.
        raise FormulaSecurityError(
            f"'{type(node).__name__}' is not allowed in a formula. Formulas "
            f"may only use spectrum aliases, numbers, +-*/**%, and the "
            f"functions listed in the reference panel."
        )


class SpectralCalculatorManager:
    """Business logic for the spectral calculator.

    Evaluates a user-defined formula string where spectrum labels are
    replaced by their numpy y-scale arrays.  All spectra must share an
    identical x-axis — use Define Spectral Range with linearisation first
    if they differ.
    """

    # Built-in functions exposed to formulas — spectroscopy-relevant set
    SAFE_FUNCTIONS = {
        # Element-wise math — these return an array of the same shape
        'abs':    np.abs,
        'sqrt':   np.sqrt,
        'log':    np.log,
        'log10':  np.log10,
        'log2':   np.log2,
        'exp':    np.exp,
        'sin':    np.sin,
        'cos':    np.cos,
        'cumsum': np.cumsum,
        # Spectroscopy transforms — all element-wise, preserve sign correctly
        # absorbance: A = -log10(T).  Works for T in (0,1] and handles negatives
        # by clipping to a small positive floor to avoid log(0) / log(negative).
        'absorbance':    lambda T: -np.log10(np.clip(T, 1e-10, None)),
        # transmittance: T = 10^(-A).  Exact inverse of absorbance above.
        'transmittance': lambda A: 10.0 ** (-A),
        'kubelka_munk':  lambda R: (1.0 - np.clip(R, 1e-10, 1.0 - 1e-10))**2
                                   / (2.0 * np.clip(R, 1e-10, 1.0 - 1e-10)),
        'derivative':    lambda y: np.gradient(y),
        'second_deriv':  lambda y: np.gradient(np.gradient(y)),
        'normalise':     lambda y: (y - np.min(y)) / (np.max(y) - np.min(y) + 1e-12),
        'snv':           lambda y: (y - np.mean(y)) / (np.std(y) + 1e-12),
        # Scalar reductions — useful as part of an expression e.g. sp1 - mean(sp1)
        # but cannot be used alone as the result of a formula
        'mean_val': np.mean,    # returns scalar; use in expressions: sp1 / mean_val(sp1)
        'sum_val':  np.sum,
        'min_val':  np.min,
        'max_val':  np.max,
        # constants
        'pi': np.pi,
        'e':  np.e,
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, formula: str, spectra: list) -> list:
        """Evaluate *formula* using the provided *spectra*.

        Parameters
        ----------
        formula : str
            Expression string, e.g. ``"2*sp1 + sp2 - sp3"`` or
            ``"absorbance(sp1 / sp2)"``. May also evaluate to a Python list
            of such expressions, e.g. ``"[sp1 - mean_val(sp1), sp2 - mean_val(sp2)]"``,
            to produce several output spectra from one formula instead of one.
        spectra : list
            List of spectrum dicts from the main application.

        Returns
        -------
        list
            One or more new spectrum dicts, each with keys ``x_scale``,
            ``y_scale``, ``label``, ``metadata``. A formula returning a
            single array produces a 1-element list; a formula returning a
            list/tuple of arrays produces one element per array, all
            sharing the same x-axis as the inputs.

        Raises
        ------
        ValueError
            On unknown identifier, empty result, shape mismatch, or
            evaluation failure.
        """
        if not formula.strip():
            raise ValueError("Formula is empty.")

        # Build label → spectrum mapping
        label_map = {s['label']: s for s in spectra}

        # Find which spectrum labels appear in the formula, and substitute
        # them with safe variable names — done together, in one longest-
        # label-first pass using unique masking tokens, rather than two
        # separate passes (a plain substring search to DETECT usage, then
        # a second pass to substitute).
        #
        # A plain substring search for detection has a real failure mode:
        # this app auto-uniquifies duplicate labels as "Name", "Name (2)",
        # "Name (3)", ... (see spectrum_manager.py) — so "Name" is a
        # genuine substring of "Name (2)" in completely ordinary usage,
        # not a contrived edge case. A formula that only ever mentions
        # "Name (2)" would previously also flag "Name" as "used" (since
        # "Name" trivially matches inside "Name (2)"), pulling an
        # unrelated, never-referenced spectrum into the x-axis check and
        # producing a confusing "different x-axes" error about a spectrum
        # the formula never touched — or, if both existed with the same
        # axis, silently exposing a spectrum variable the user never
        # actually asked for.
        #
        # The single masking pass below avoids this categorically: for
        # each label, longest first, every occurrence found in the
        # formula is immediately replaced with a random, formula-text-safe
        # placeholder token before the next (shorter) label is searched
        # for — so a shorter label can never be found "inside" a longer
        # one's text, because that text is already gone from what's being
        # searched by the time the shorter label's turn comes.
        working = formula
        used_labels = []
        placeholder_for_label = {}
        for lbl in sorted(label_map, key=len, reverse=True):
            if lbl in working:
                used_labels.append(lbl)
                # NUL-wrapped random token: cannot collide with any real
                # label text or formula syntax, and is trivially distinct
                # from every other label's own placeholder.
                placeholder = f'\x00{uuid.uuid4().hex}\x00'
                placeholder_for_label[lbl] = placeholder
                working = working.replace(lbl, placeholder)

        if not used_labels:
            raise ValueError(
                "No spectrum labels found in the formula. "
                "Make sure the labels in the formula exactly match the spectrum names."
            )

        eval_formula = working
        for lbl in used_labels:
            eval_formula = eval_formula.replace(placeholder_for_label[lbl], self._safe_var_name(lbl))

        # Verify all used spectra share an identical x-axis
        common_x, arrays = self._require_identical_x(
            [label_map[lbl] for lbl in used_labels]
        )

        # Build the name -> array mapping for the safe evaluator.
        names = {}
        for lbl, arr in zip(used_labels, arrays):
            names[self._safe_var_name(lbl)] = arr

        # Functions available to formulas. derivative/second_deriv are
        # overridden here (rather than used straight from SAFE_FUNCTIONS)
        # to use the actual x-axis spacing — np.gradient(y) alone assumes
        # spacing=1, np.gradient(y, x) uses the real spacing.
        functions = {k: v for k, v in self.SAFE_FUNCTIONS.items() if k not in ('pi', 'e')}
        functions['derivative']   = lambda y: np.gradient(y, common_x)
        functions['second_deriv'] = lambda y: np.gradient(np.gradient(y, common_x), common_x)
        constants = {'pi': self.SAFE_FUNCTIONS['pi'], 'e': self.SAFE_FUNCTIONS['e']}

        logger.debug(f"Evaluating formula: '{eval_formula}'")

        # NEVER eval()/exec() the formula — see _SafeFormulaEvaluator's
        # docstring for exactly why that's not actually a sandbox. This
        # parses to an AST and walks a hand-picked whitelist of node
        # types instead; there is no attribute-access node type in that
        # whitelist, so there is no path from here to __class__ or any
        # other object-graph escape.
        evaluator = _SafeFormulaEvaluator(names, functions, constants)
        try:
            result = evaluator.evaluate(eval_formula)
        except (ValueError, FormulaSecurityError):
            raise
        except Exception as exc:
            raise ValueError(f"Formula evaluation failed: {exc}") from exc

        # A formula returning a Python list or tuple produces MULTIPLE output
        # spectra, one per element — checked before np.asarray() because
        # numpy would otherwise try to stack a list of equal-length arrays
        # into a single 2D array, which is not what we want here (each
        # element must become its own separate, independently-validated
        # 1D output spectrum, not a column of a combined matrix).
        if isinstance(result, (list, tuple)):
            result_arrays = list(result)
            if not result_arrays:
                raise ValueError("Formula returned an empty list — expected at least one result.")
        else:
            result_arrays = [result]

        outputs = []
        for idx, single_result in enumerate(result_arrays):
            result_y = np.asarray(single_result, dtype=float)
            if result_y.shape != common_x.shape:
                where = '' if len(result_arrays) == 1 else f' (output {idx + 1} of {len(result_arrays)})'
                raise ValueError(
                    f"Result shape {result_y.shape} does not match x-axis shape "
                    f"{common_x.shape}{where}. Ensure the formula returns one value per point."
                )
            outputs.append({
                'x_scale': common_x.copy(),
                'y_scale': result_y.copy(),
                'label': 'calculator_result',
                'metadata': {
                    'creation_method': 'spectral_calculator',
                    'formula': formula,
                    'source_spectra': used_labels,
                    'source_spectra_count': len(used_labels),
                    'output_index': idx,
                    'output_count': len(result_arrays),
                    'creation_timestamp': datetime.now().isoformat(),
                },
            })
            # Shared, chronologically-ordered history mechanism (see
            # correction_history.py) — started fresh here since each
            # output is a brand-new spectrum with no prior history of its
            # own, same reasoning as Combine Spectra's own result entry.
            outputs[-1]['metadata']['correction_history'] = append_correction_history(
                None, 'Spectral Calculator',
                {
                    'formula': formula,
                    'source_spectra': used_labels,
                    'source_spectra_count': len(used_labels),
                    'output_index': idx,
                    'output_count': len(result_arrays),
                }
            )

        return outputs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_var_name(label: str) -> str:
        """Convert a spectrum label to a valid Python identifier."""
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in label)
        if safe and safe[0].isdigit():
            safe = '_' + safe
        return f'_sp_{safe}'

    @staticmethod
    def _require_identical_x(spectra: list):
        """Return (common_x, list_of_y_arrays) if all spectra share an identical
        x-axis, otherwise raise ValueError directing the user to linearise first.
        """
        x_scales = [np.asarray(s['x_scale'], dtype=float) for s in spectra]
        y_scales = [np.asarray(s['y_scale'], dtype=float) for s in spectra]

        ref = x_scales[0]
        for i, x in enumerate(x_scales[1:], start=1):
            # Uses the shared, tolerance-aware comparison (spectra_validation.
            # axes_match) rather than a bare np.allclose(). np.allclose's DEFAULT
            # rtol is 1e-5 — on a 1000 cm-1 axis that is a tolerance of ~0.01
            # cm-1, so two genuinely different grids offset by, say, 0.009 cm-1
            # were accepted as "identical" and their points then paired up
            # one-for-one in the formula. axes_match scales the tolerance to the
            # data instead (one millionth of the median step), which is far below
            # any instrument's precision yet far above float round-off.
            if not axes_match(ref, x):
                label_a = spectra[0]['label']
                label_b = spectra[i]['label']
                raise ValueError(
                    f"Spectra '{label_a}' and '{label_b}' have different x-axes "
                    f"({len(ref)} vs {len(x)} points). "
                    f"Please use Define Spectral Range with 'Apply linearisation' "
                    f"to bring all spectra onto a common x-axis before using the "
                    f"Spectral Calculator."
                )

        return ref.copy(), [y.copy() for y in y_scales]

    def validate_formula(self, formula: str, spectra: list) -> str:
        """Return an error message string, or empty string if the formula is valid."""
        try:
            self.evaluate(formula, spectra)
            return ''
        except Exception as exc:
            return str(exc)

    @staticmethod
    def available_functions() -> list:
        """Return a list of (name, description) tuples for the reference panel."""
        return [
            # Element-wise — safe to use as formula result
            ('abs(x)',           'Element-wise absolute value'),
            ('sqrt(x)',          'Element-wise square root'),
            ('log(x)',           'Natural logarithm ln(x)'),
            ('log10(x)',         'Base-10 logarithm'),
            ('log2(x)',          'Base-2 logarithm'),
            ('exp(x)',           'Exponential e^x'),
            ('sin(x)',           'Sine'),
            ('cos(x)',           'Cosine'),
            ('cumsum(x)',        'Cumulative sum (element-wise)'),
            # Spectroscopy transforms
            ('absorbance(x)',    'A = -log10(T)  — transmittance to absorbance'),
            ('transmittance(x)', 'T = 10^(-A)    — absorbance to transmittance'),
            ('kubelka_munk(x)',  'F(R) = (1-R)^2 / (2R)  — diffuse reflectance'),
            ('derivative(x)',    'First derivative (np.gradient)'),
            ('second_deriv(x)',  'Second derivative'),
            ('normalise(x)',     'Min-max normalisation to [0, 1]'),
            ('snv(x)',           'Standard Normal Variate'),
            # Scalar reductions — use inside expressions only
            ('mean_val(x)',      'Returns scalar mean — use inside expression: sp1 - mean_val(sp1)'),
            ('sum_val(x)',       'Returns scalar sum — use inside expression: sp1 / sum_val(sp1)'),
            ('min_val(x)',       'Returns scalar minimum — use inside expression: sp1 - min_val(sp1)'),
            ('max_val(x)',       'Returns scalar maximum — use inside expression: sp1 / max_val(sp1)'),
        ]
