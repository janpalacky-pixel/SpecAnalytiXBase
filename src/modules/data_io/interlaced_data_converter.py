# src/modules/data_io/interlaced_data_converter.py

import numpy as np
from typing import List, Dict, Union, Tuple, Optional
from datetime import datetime
import os
import re
from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

def read_interlaced_data(
    filepath: str,
    delimiter: Optional[str] = None,
    decimal_separator: Optional[str] = None,
    header: Optional[bool] = None,
    analyze_rows: int = 20,
    zero_padding: int = 4,
    header_threshold: float = 0.5,
) -> List[Dict[str, Union[np.ndarray, str, Dict]]]:
    """
    Read and parse interlaced tabular data containing multiple spectra.
    In interlaced format, each spectrum is represented by pairs of x-scale and y-scale columns.
    
    Parameters:
    -----------
    filepath : str
        Path to the input file
    delimiter : str, optional
        Value separator character (default: None, auto-detect)
    decimal_separator : str, optional
        Decimal separator character, either '.' or ',' (default: None, auto-detect)
    header : bool, optional
        Whether the data contains a header (default: None, auto-detect)
    analyze_rows : int, optional
        Number of rows to analyze for auto-detection (default: 20)
    zero_padding : int, optional
        Number of digits for automatic numbering (default: 4)
    header_threshold : float, optional
        Fraction (0.0-1.0) of non-numeric tokens required to auto-detect
        the first line as a header. Only used when `header` is None.
        Default 0.5 (50%).
        
    Returns:
    --------
    List[Dict]
        List of spectrum dictionaries, each containing:
        - x_scale: np.ndarray
        - y_scale: np.ndarray
        - label: str
        - metadata: Dict
    """
    # Read raw data as strings to preserve original format
    raw_data = _read_raw_data(filepath)
    if not raw_data:
        raise ValueError("Empty file or no valid data found")
    
    # Auto-detect delimiter and decimal separator if not specified
    if delimiter is None or decimal_separator is None:
        detected_decimal, detected_delimiter = _detect_separators(raw_data, analyze_rows)
        decimal_separator = decimal_separator or detected_decimal
        delimiter = delimiter or detected_delimiter
    
    # Auto-detect header if not specified
    if header is None:
        header = _detect_header(raw_data, delimiter, decimal_separator, analyze_rows, header_threshold)
    
    # Parse interlaced column data
    return _parse_interlaced_column_data(
        raw_data,
        filepath,
        delimiter,
        decimal_separator,
        header,
        zero_padding
    )

def _detect_header(raw_data: List[str], delimiter: str, decimal_separator: str,
                    analyze_rows: int, threshold: float = 0.5) -> bool:
    """Detect if first line is a header.

    threshold : fraction (0.0-1.0) of tokens that must be non-numeric for
                the line to be classified as a header. Default 0.5 (50%).
    """
    if not raw_data:
        return False
    
    first_line = raw_data[0]
    parts = _split_line(first_line, delimiter)
    
    # Count non-numeric parts
    non_numeric = 0
    for part in parts:
        part = part.strip()
        if part:
            try:
                # Try to convert to float
                test_part = part.replace(decimal_separator, '.') if decimal_separator == ',' else part
                float(test_part)
            except ValueError:
                non_numeric += 1
    
    # If the non-numeric fraction reaches the threshold, it's probably a header
    has_header = len(parts) > 0 and non_numeric >= len(parts) * threshold
    logger.debug(f"Header check: {non_numeric}/{len(parts)} non-numeric parts (threshold={threshold*100:.0f}%)")
    return has_header

def _read_raw_data(filepath: str) -> List[str]:
    """Read raw data from file as strings with encoding handling.

    IMPORTANT: uses rstrip (not strip) so that leading tabs are preserved.
    Leading tabs represent empty fields at the start of a row in interlaced
    tab-separated files where a shorter spectrum has run out of data while a
    longer spectrum in a later column pair still has rows.  Calling strip()
    would remove those leading tabs and shift all column indices leftward,
    causing the interlaced parser to map every column to the wrong spectrum.
    """
    lines = []
    
    # Try multiple encodings
    for encoding in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                for line in f:
                    # Strip only line endings — do NOT strip leading whitespace/tabs,
                    # because leading tabs are meaningful field separators in
                    # interlaced files where early column pairs contain NaN.
                    line = line.rstrip('\r\n')
                    # Remove BOM if present at the very start of the file
                    if line.startswith('\ufeff'):
                        line = line[1:]
                    # Skip lines that are truly blank (no content at all)
                    if line.strip():
                        lines.append(line)
            break
        except UnicodeDecodeError:
            continue
    
    return lines

def _detect_separators(raw_data: List[str], analyze_rows: int) -> Tuple[str, str]:
    """Detect decimal and value separators from file content."""
    analyze_rows = min(analyze_rows, len(raw_data))
    lines = raw_data[:analyze_rows]
    
    delimiter_counts = {
        ';': sum(line.count(';') for line in lines),
        '\t': sum(line.count('\t') for line in lines),
        ',': sum(line.count(',') for line in lines),
        '|': sum(line.count('|') for line in lines)
    }
    
    # Check for tab delimiter with consistent column structure
    if delimiter_counts['\t'] > 0:
        tab_split_counts = [len(line.split('\t')) for line in lines]
        if len(tab_split_counts) > 0 and tab_split_counts.count(tab_split_counts[0]) == len(tab_split_counts) and tab_split_counts[0] > 1:
            samples = []
            for line in lines:
                samples.extend([item.strip() for item in line.split('\t') if item.strip()])
            
            # Count decimal patterns
            dot_pattern = re.compile(r'\d+\.\d+')
            comma_pattern = re.compile(r'\d+,\d+')
            dot_count = sum(1 for s in samples if dot_pattern.search(s))
            comma_count = sum(1 for s in samples if comma_pattern.search(s))
            
            decimal_sep = ',' if comma_count > dot_count else '.'
            return decimal_sep, '\t'
    
    # Check for consistent delimiter usage (semicolon or pipe)
    for delim in (';', '|'):
        if delimiter_counts[delim] > 0 and all(line.count(delim) == lines[0].count(delim) for line in lines[1:]):
            samples = []
            for line in lines:
                samples.extend([part.strip() for part in line.split(delim) if part.strip()])
            
            # Count decimal patterns
            dot_pattern = re.compile(r'\d+\.\d+')
            comma_pattern = re.compile(r'\d+,\d+')
            dot_count = sum(1 for s in samples if dot_pattern.search(s))
            comma_count = sum(1 for s in samples if comma_pattern.search(s))
            
            decimal_sep = ',' if comma_count > dot_count else '.'
            return decimal_sep, delim
    
    # Detect decimal separator from number patterns
    cleaned_lines = [re.sub(r'[eE][+-]?\d+', '', line) for line in lines]
    dot_count = sum(len(re.findall(r'\d\.\d', line)) for line in cleaned_lines)
    comma_count = sum(len(re.findall(r'\d,\d', line)) for line in cleaned_lines)
    decimal_sep = ',' if comma_count > dot_count else '.'
    
    # Detect value separator
    possible_seps = ['\t', ';', '|', ',', r'\s+']
    sep_counts = {sep: 0 for sep in possible_seps}
    
    for line in cleaned_lines:
        cleaned_line = re.sub(r'\d+[.,]\d+', 'NUM', line)
        for sep in possible_seps:
            if sep == r'\s+':
                tokens = [t for t in re.split(r'\s+', cleaned_line.strip()) if t]
                sep_counts[sep] += len(tokens) - 1 if len(tokens) > 1 else 0
            elif sep == '\t':
                tokens = [t for t in cleaned_line.split('\t') if t]
                sep_counts[sep] += len(tokens) - 1 if len(tokens) > 1 else 0
            else:
                sep_counts[sep] += cleaned_line.count(sep)
    
    # Check for consistent whitespace separation
    if sep_counts[r'\s+'] > 0:
        first_line_count = len([t for t in re.split(r'\s+', lines[0].strip()) if t])
        whitespace_consistent = all(
            len([t for t in re.split(r'\s+', line.strip()) if t]) == first_line_count
            for line in lines[1:]
        )
        if whitespace_consistent and first_line_count > 1:
            return decimal_sep, r'\s+'
    
    # Choose the most frequent separator
    value_sep_candidates = {k: v for k, v in sep_counts.items() if k != r'\s+'}
    if value_sep_candidates:
        value_sep = max(value_sep_candidates.items(), key=lambda x: x[1])[0] 
        if sep_counts[value_sep] > 0:
            return decimal_sep, value_sep
    
    # Fallback logic
    if sep_counts[r'\s+'] > 0:
        return decimal_sep, r'\s+'
    
    if delimiter_counts['\t'] > 0:
        return decimal_sep, '\t'
    elif delimiter_counts[';'] > 0:
        return decimal_sep, ';'
    elif delimiter_counts[','] > decimal_sep.count(','):
        return decimal_sep, ','
    elif delimiter_counts['|'] > 0:
        return decimal_sep, '|'
    
    return decimal_sep, r'\s+'

def _convert_to_float(value: str, decimal_separator: str) -> float:
    """Convert string to float handling different decimal separators."""
    try:
        if not value.strip():
            return np.nan
            
        clean_value = value.strip()
        if decimal_separator == ',':
            clean_value = clean_value.replace(',', '.')
        
        # Handle scientific notation
        clean_value = re.sub(r'[eE]\+', 'e+', clean_value)
        clean_value = re.sub(r'[eE](?=[0-9])', 'e+', clean_value)
        clean_value = re.sub(r'[eE]-', 'e-', clean_value)
        
        return float(clean_value)
    except (ValueError, TypeError):
        return np.nan

def _split_line(line: str, delimiter: str) -> List[str]:
    """Split line using the specified delimiter."""
    if delimiter == r'\s+':
        return [token for token in re.split(r'\s+', line.strip()) if token]
    elif delimiter == '\t':
        return [token.strip() for token in line.split('\t')]
    return [token.strip() for token in line.split(delimiter)]

def _parse_interlaced_column_data(
    raw_data: List[str],
    filepath: str,
    delimiter: str,
    decimal_separator: str,
    header: bool,
    zero_padding: int
) -> List[Dict]:
    """Parse interlaced column-oriented data - creates spectra from x,y column pairs."""
    # Extract header if present
    labels = []
    data_to_process = raw_data.copy()
    
    if header and len(data_to_process) > 0:
        header_line = data_to_process[0]
        labels = _split_line(header_line, delimiter)
        data_to_process = data_to_process[1:]
    
    # Parse data based on delimiter type
    if delimiter == '\t':
        # Special handling for tab-separated data
        max_fields = 0
        for line in data_to_process:
            if line.strip():
                fields = line.split('\t')
                max_fields = max(max_fields, len(fields))
        
        aligned_data = []
        for line in data_to_process:
            if not line.strip():
                continue
                
            fields = line.split('\t')
            padded_fields = fields + [''] * (max_fields - len(fields))
            values = []
            for field in padded_fields:
                if field.strip():
                    try:
                        values.append(_convert_to_float(field.strip(), decimal_separator))
                    except:
                        values.append(np.nan)
                else:
                    values.append(np.nan)
            
            if any(not np.isnan(v) for v in values):
                aligned_data.append(values)
        
        if not aligned_data:
            return []
            
        data_array = np.array(aligned_data)
        
    else:
        # Handle other delimiters
        data_rows = []
        for line in data_to_process:
            values = [_convert_to_float(val.strip(), decimal_separator) 
                     for val in _split_line(line, delimiter)]
            if len(values) > 1 and not all(np.isnan(values)):
                data_rows.append(values)
        
        if not data_rows:
            return []
        
        # Pad to make rectangular array
        max_cols = max(len(row) for row in data_rows)
        padded_data = []
        for row in data_rows:
            padded_row = row.copy()
            while len(padded_row) < max_cols:
                padded_row.append(np.nan)
            padded_data.append(padded_row)
        
        data_array = np.array(padded_data)
    
    # Create spectra from x,y column pairs
    spectra = []
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    
    # Process columns in x,y pairs: (0,1), (2,3), (4,5), etc.
    num_pairs = data_array.shape[1] // 2
    logger.debug(f"DEBUG INTERLACED: Processing {num_pairs} x,y pairs from {data_array.shape[1]} columns")
    
    for pair_idx in range(num_pairs):
        x_col_idx = pair_idx * 2      # 0, 2, 4, 6...
        y_col_idx = pair_idx * 2 + 1  # 1, 3, 5, 7...
        
        if y_col_idx >= data_array.shape[1]:
            break
            
        # Extract x,y data
        x_values = data_array[:, x_col_idx]
        y_values = data_array[:, y_col_idx]
        
        # Remove invalid data points
        valid_mask = ~(np.isnan(x_values) | np.isnan(y_values))
        x_filtered = x_values[valid_mask]
        y_filtered = y_values[valid_mask]
        
        if len(x_filtered) < 2:
            continue
        
        # Sorting and duplicate-x merging both happen centrally now, in
        # spectrum_manager.py (_sort_spectrum_by_x / _merge_duplicate_x) —
        # the single door every import format passes through — rather than
        # here. Previously this converter did both itself, which is exactly
        # how "only plain-text interlaced merges duplicates" became
        # inconsistent with every other format. x_filtered/y_filtered are
        # passed through as-is; the central step sorts and merges them
        # after this function returns.
        x_scale, y_scale = x_filtered, y_filtered

        # Generate spectrum label
        if labels and y_col_idx < len(labels) and labels[y_col_idx].strip():
            # Use y-column header label
            header_label = re.sub(r'[^\w\s-]', '', labels[y_col_idx].strip())
            header_label = re.sub(r'[-\s]+', '_', header_label).strip('-_')
            label = f"{base_name} : {header_label}"
        else:
            # Auto-generate label
            if num_pairs == 1:
                label = base_name
            else:
                label = f"{base_name} : {str(pair_idx+1).zfill(zero_padding)}"
        
        # Create metadata
        metadata = {
            'file_path': filepath,
            'file_type': 'interlaced_table',
            'original_label': label,
            'spectrum_name': label,
            'interlaced_pair_index': pair_idx,
            'valid_points': len(x_scale),
            'x_column_index': x_col_idx,
            'y_column_index': y_col_idx,
            'file_creation_time': datetime.fromtimestamp(os.path.getctime(filepath)).isoformat(),
            'file_modification_time': datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
        }
        
        spectra.append({
            'x_scale': x_scale,
            'y_scale': y_scale,
            'label': label,
            'metadata': metadata
        })
        
        logger.info(f"✅ Created interlaced spectrum '{label}': {len(x_scale)} points")
    
    return spectra