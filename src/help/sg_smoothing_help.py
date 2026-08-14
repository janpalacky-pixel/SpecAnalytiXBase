# src/help/sg_smoothing_help.py

def get_sg_smoothing_help_title():
    """Return the title for SG-smoothing help."""
    return "Savitzky-Golay Smoothing Help"

def get_sg_smoothing_help_content():
    """Return HTML content for SG-smoothing help."""
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2 { color: #1976D2; margin-top: 25px; }
            h3 { color: #F57C00; margin-top: 20px; }
            .method-category { background-color: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .warning { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; }
            .tip { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; }
            .danger { background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; border-radius: 5px; }
            .formula { background-color: #e9ecef; padding: 5px; font-family: monospace; border-radius: 3px; }
            ul { padding-left: 20px; }
            li { margin: 5px 0; }
            .parameter-box { background-color: #e8f5e8; padding: 10px; margin: 5px 0; border-left: 4px solid #4caf50; }
        </style>
    </head>
    <body>
        <h1>Savitzky-Golay Smoothing Help</h1>
        
        <h2>Overview</h2>
        <p>The Savitzky-Golay filter is a digital smoothing filter that preserves features of the original data while reducing noise. Unlike simple moving averages, it fits local polynomial functions to data points, making it excellent for spectroscopic applications where peak shapes and positions must be preserved.</p>
        
        <div class="tip">
            <strong>Key Advantage:</strong> Savitzky-Golay smoothing preserves peak positions, widths, and relative intensities better than other smoothing methods while effectively reducing noise.
        </div>
        
        <h2>How It Works</h2>
        <p>The filter works by:</p>
        <ol>
            <li><strong>Local Polynomial Fitting:</strong> For each data point, fits a polynomial to a window of surrounding points</li>
            <li><strong>Point Replacement:</strong> Replaces the center point with the polynomial-predicted value</li>
            <li><strong>Window Sliding:</strong> Moves the window along the data, repeating the process</li>
            <li><strong>Derivative Calculation:</strong> Optionally calculates derivatives using the fitted polynomials</li>
        </ol>
        
        <h2>Parameters Explained</h2>
        
        <div class="parameter-box">
            <h3>Window Length</h3>
            <p><strong>Description:</strong> Number of data points used for polynomial fitting (must be odd)</p>
            <p><strong>Effect:</strong></p>
            <ul>
                <li><strong>Smaller window (3-7 points):</strong> Less smoothing, preserves fine details, more noise remains</li>
                <li><strong>Medium window (9-15 points):</strong> Good balance of smoothing and feature preservation</li>
                <li><strong>Larger window (17+ points):</strong> More aggressive smoothing, may distort narrow peaks</li>
            </ul>
            <p><strong>Recommendation:</strong> Start with 9-11 points for typical spectroscopic data</p>
        </div>
        
        <div class="parameter-box">
            <h3>Polynomial Order</h3>
            <p><strong>Description:</strong> Degree of polynomial used for local fitting (must be less than window length)</p>
            <p><strong>Common Values:</strong></p>
            <ul>
                <li><strong>Order 2-3:</strong> Good for most spectroscopic applications with smooth baselines</li>
                <li><strong>Order 4-5:</strong> Better for data with more complex curvature</li>
                <li><strong>Higher orders:</strong> May introduce artifacts or overfit to noise</li>
            </ul>
            <p><strong>Recommendation:</strong> Use order 2-3 for most cases; increase only if baseline curvature is complex</p>
        </div>
        
        <div class="parameter-box">
            <h3>Derivative Order</h3>
            <p><strong>Description:</strong> Calculate derivatives while smoothing</p>
            <p><strong>Options:</strong></p>
            <ul>
                <li><strong>0 (default):</strong> Smoothing only, no derivatives</li>
                <li><strong>1:</strong> First derivative (slope, useful for peak detection)</li>
                <li><strong>2:</strong> Second derivative (curvature, enhances peak resolution)</li>
                <li><strong>Higher orders:</strong> Rarely used, may amplify noise</li>
            </ul>
            <p><strong>Note:</strong> Derivatives can enhance spectral features but may also amplify noise</p>
        </div>
        
        <div class="parameter-box">
            <h3>Delta Values</h3>
            <p><strong>Description:</strong> Spacing between consecutive data points in your units</p>
            <p><strong>Importance:</strong></p>
            <ul>
                <li><strong>For smoothing only (deriv = 0):</strong> Delta has minimal impact</li>
                <li><strong>For derivatives:</strong> Critical for correct scaling of derivative values</li>
                <li><strong>Non-uniform spacing:</strong> May cause artifacts in derivative calculation</li>
            </ul>
            <p><strong>Auto-detection:</strong> The program estimates delta from your data's median point spacing</p>
            <div class="tip">
                <strong>Custom Delta Values:</strong> Use "Set Individual Delta Values" to specify exact spacing for each spectrum when auto-detection is insufficient.
            </div>
        </div>
        
        <div class="parameter-box">
            <h3>Edge Mode</h3>
            <p><strong>Description:</strong> How to handle data points near spectrum edges</p>
            <p><strong>Options:</strong></p>
            <ul>
                <li><strong>interp (default):</strong> Interpolates edge values, usually best choice</li>
                <li><strong>constant:</strong> Extends edges with constant values</li>
                <li><strong>nearest:</strong> Uses nearest valid data point</li>
                <li><strong>mirror:</strong> Reflects data at edges</li>
                <li><strong>wrap:</strong> Treats data as periodic</li>
            </ul>
            <p><strong>Recommendation:</strong> Keep default 'interp' unless you have specific edge requirements</p>
        </div>
        
        <h2>Usage Guidelines</h2>
        
        <h3>For Different Applications</h3>
        
        <div class="method-category">
            <h3>Basic Noise Reduction</h3>
            <ul>
                <li><strong>Window Length:</strong> 9-15 points</li>
                <li><strong>Polynomial Order:</strong> 2-3</li>
                <li><strong>Derivative Order:</strong> 0</li>
                <li><strong>Use Case:</strong> General spectroscopic noise reduction</li>
            </ul>
        </div>
        
        <div class="method-category">
            <h3>Peak Detection Enhancement</h3>
            <ul>
                <li><strong>Window Length:</strong> 7-11 points (smaller to preserve peak details)</li>
                <li><strong>Polynomial Order:</strong> 2-3</li>
                <li><strong>Derivative Order:</strong> 1 or 2</li>
                <li><strong>Use Case:</strong> Enhance peaks for automated detection</li>
            </ul>
        </div>
        
        <div class="method-category">
            <h3>Baseline-Rich Spectra</h3>
            <ul>
                <li><strong>Window Length:</strong> 11-21 points</li>
                <li><strong>Polynomial Order:</strong> 3-4</li>
                <li><strong>Derivative Order:</strong> 0</li>
                <li><strong>Use Case:</strong> Spectra with complex baselines (fluorescence, Raman)</li>
            </ul>
        </div>
        
        <div class="method-category">
            <h3>High-Resolution Data</h3>
            <ul>
                <li><strong>Window Length:</strong> 5-9 points</li>
                <li><strong>Polynomial Order:</strong> 2-3</li>
                <li><strong>Derivative Order:</strong> 0-1</li>
                <li><strong>Use Case:</strong> Preserve fine spectral features in high-resolution data</li>
            </ul>
        </div>
        
        <h2>Best Practices</h2>
        
        <h3>Parameter Selection Strategy</h3>
        <ol>
            <li><strong>Start Conservative:</strong> Begin with window length = 9, polynomial order = 2</li>
            <li><strong>Adjust Window Size:</strong> Increase for more smoothing, decrease to preserve details</li>
            <li><strong>Monitor Peak Shapes:</strong> Ensure important spectral features aren't distorted</li>
            <li><strong>Test Different Orders:</strong> Try polynomial orders 2-4 to find best balance</li>
            <li><strong>Consider Your Goal:</strong> More smoothing for quantitative analysis, less for qualitative</li>
        </ol>
        
        <h3>Quality Control</h3>
        <ul>
            <li><strong>Visual Inspection:</strong> Always compare before/after smoothing</li>
            <li><strong>Peak Preservation:</strong> Check that peak positions and intensities are maintained</li>
            <li><strong>Baseline Behavior:</strong> Ensure baseline regions aren't artificially modified</li>
            <li><strong>Noise vs. Features:</strong> Verify that real spectral features aren't over-smoothed</li>
        </ul>
        
        <h3>Common Mistakes to Avoid</h3>
        <div class="warning">
            <ul>
                <li><strong>Window Too Large:</strong> Can distort narrow peaks or create artifacts</li>
                <li><strong>Polynomial Order Too High:</strong> May overfit to noise instead of smoothing</li>
                <li><strong>Wrong Delta Values:</strong> Leads to incorrect derivative scaling</li>
                <li><strong>Over-smoothing:</strong> Loss of genuine spectral information</li>
                <li><strong>Ignoring Edge Effects:</strong> Check that spectrum edges are handled appropriately</li>
            </ul>
        </div>
        
        <h2>Technical Background</h2>
        
        <h3>Mathematical Foundation</h3>
        <p>The Savitzky-Golay method performs a least-squares fit of a polynomial to a sliding window of data points:</p>
        
        <p><strong>For smoothing:</strong></p>
        <div class="formula">y_smooth[i] = Σ(c_j × y[i+j]) where c_j are convolution coefficients</div>
        
        <p><strong>For derivatives:</strong></p>
        <div class="formula">y'[i] = (1/delta) × Σ(d_j × y[i+j]) where d_j are derivative coefficients</div>
        
        <h3>Why It Works Well for Spectroscopy</h3>
        <ul>
            <li><strong>Peak Preservation:</strong> Polynomial fitting naturally preserves Gaussian and Lorentzian peak shapes</li>
            <li><strong>Local Adaptation:</strong> Each point is fit independently, adapting to local spectral features</li>
            <li><strong>Derivative Capability:</strong> Provides smooth derivatives for peak analysis</li>
            <li><strong>Minimal Phase Distortion:</strong> Unlike many filters, doesn't shift peak positions</li>
        </ul>
        
        <h2>Individual Delta Value Settings</h2>
        
        <p>The "Set Individual Delta Values" feature allows precise control over spacing parameters for each spectrum:</p>
        
        <h3>When to Use Individual Delta Values</h3>
        <ul>
            <li><strong>Mixed Data Types:</strong> Different spectra with different x-axis units or spacing</li>
            <li><strong>Derivative Calculations:</strong> When accurate derivative scaling is critical</li>
            <li><strong>Non-uniform Spacing:</strong> When automatic detection fails due to irregular sampling</li>
            <li><strong>Precision Requirements:</strong> For quantitative derivative analysis</li>
        </ul>
        
        <h3>Understanding the Delta Table</h3>
        <ul>
            <li><strong>Estimated Delta:</strong> Auto-calculated median spacing between consecutive points</li>
            <li><strong>Variance:</strong> Indicates spacing uniformity (highlighted if high)</li>
            <li><strong>Custom Delta:</strong> Your manually specified spacing value</li>
        </ul>
        
        <div class="tip">
            <strong>Delta Validation:</strong> High variance (highlighted in yellow) suggests non-uniform spacing that may affect derivative quality.
        </div>

        <h2>Committing Your Filter</h2>
        <p>Once the window length, polynomial order, and derivative settings look right in the
        preview, use the buttons at the bottom of the dialog to commit:</p>
        <ul>
            <li><strong>Apply</strong> replaces the selected spectra with their smoothed result.
            The originals are overwritten once Apply runs.</li>
            <li><strong>Add as New</strong> leaves the originals completely untouched and adds the
            smoothed result to the spectra list under new, unique names (e.g.
            <span class="formula">samplename_smoothed</span>, with a number appended if that name
            is already taken).</li>
            <li><strong>Close</strong> closes the dialog without applying anything to the main
            window's spectra. Whatever settings were last shown are still remembered the next time
            you reopen it for the same spectra.</li>
        </ul>
        <p>There is no separate Run step in the main window for this operation — Apply and Add as
        New commit immediately, after which the dialog closes automatically.</p>
        
        <h2>Troubleshooting</h2>
        
        <h3>Common Issues and Solutions</h3>
        
        <div class="danger">
            <h4>Problem: Smoothed spectra look distorted</h4>
            <p><strong>Causes:</strong> Window length too large, polynomial order too high</p>
            <p><strong>Solutions:</strong> Reduce window length, try lower polynomial order</p>
        </div>
        
        <div class="danger">
            <h4>Problem: Not enough noise reduction</h4>
            <p><strong>Causes:</strong> Window length too small, polynomial order too low</p>
            <p><strong>Solutions:</strong> Increase window length gradually, try polynomial order 3-4</p>
        </div>
        
        <div class="danger">
            <h4>Problem: Peaks are shifted or broadened</h4>
            <p><strong>Causes:</strong> Inappropriate parameters, edge effects</p>
            <p><strong>Solutions:</strong> Reduce window length, check edge mode settings</p>
        </div>
        
        <div class="danger">
            <h4>Problem: Derivatives have wrong scale</h4>
            <p><strong>Causes:</strong> Incorrect delta values</p>
            <p><strong>Solutions:</strong> Set individual delta values manually, check x-axis units</p>
        </div>
        
        <h2>Advanced Tips</h2>
        
        <h3>Spectral Type Considerations</h3>
        <ul>
            <li><strong>IR Spectroscopy:</strong> Moderate smoothing (window 9-15), preserve sharp absorption bands</li>
            <li><strong>Raman Spectroscopy:</strong> Light smoothing (window 7-11), preserve peak asymmetry</li>
            <li><strong>UV-Vis Spectroscopy:</strong> Can use more aggressive smoothing (window 11-21)</li>
            <li><strong>Fluorescence:</strong> Often benefits from higher polynomial orders (3-4) due to broad features</li>
            <li><strong>NMR:</strong> Very light smoothing to preserve coupling patterns</li>
        </ul>
        
        <h3>Integration with Other Operations</h3>
        <ul>
            <li><strong>Before Baseline Correction:</strong> Smoothing can make baseline fitting more stable</li>
            <li><strong>Before Peak Detection:</strong> Light smoothing improves automated peak finding</li>
            <li><strong>After Normalization:</strong> Apply normalization first, then smooth to avoid scaling artifacts</li>
            <li><strong>Before Derivatives:</strong> Use derivative order parameter rather than separate differentiation</li>
        </ul>
        
        <div class="tip">
            <h3>Pro Tips for Spectroscopic Analysis</h3>
            <ul>
                <li><strong>Save Original Data:</strong> Always keep unprocessed spectra for comparison</li>
                <li><strong>Document Parameters:</strong> Record all smoothing parameters for reproducibility</li>
                <li><strong>Validate Results:</strong> Check that conclusions don't change with reasonable parameter variations</li>
                <li><strong>Consider Noise Sources:</strong> Electronic noise may need different treatment than chemical background</li>
                <li><strong>Test on Standards:</strong> Use reference spectra to validate parameter choices</li>
            </ul>
        </div>
        
        <h2>Literature and References</h2>
        
        <p>The Savitzky-Golay method was introduced in:</p>
        <p><em>Savitzky, A. and Golay, M.J.E. (1964) "Smoothing and Differentiation of Data by Simplified Least Squares Procedures." Analytical Chemistry, 36(8), 1627-1639.</em></p>
        
        <p>For spectroscopic applications, see:</p>
        <ul>
            <li>Steinier, J. et al. (1972) Comments on smoothing and differentiation of data by simplified least squares procedure. Analytical Chemistry, 44(11), 1906-1909.</li>
            <li>Press, W.H. et al. (2007) Numerical Recipes: The Art of Scientific Computing, 3rd Edition, Chapter 14.8.</li>
        </ul>
        
        <div class="tip">
            <strong>Remember:</strong> Savitzky-Golay smoothing is a powerful tool for spectroscopic data processing, but like all smoothing methods, it involves a trade-off between noise reduction and information preservation. Always validate that your chosen parameters preserve the spectral information you need for your analysis.
        </div>
        
    </body>
    </html>
    """