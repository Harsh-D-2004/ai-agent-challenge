import camelot
import pandas as pd
import numpy as np
import os

pdf_path = "data/icici/icici sample.pdf"
output_csv_path = "custom_parser/result.csv"

# Ensure output directory exists
os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

# Define the expected headers based on the sample content for consistency
expected_headers = ['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance']

# Extract tables from all pages using the 'lattice' flavor for structured tables
tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')

all_extracted_dfs = []

if not tables:
    # If no tables are found, create an empty DataFrame with expected headers
    parsed_df = pd.DataFrame(columns=expected_headers)
else:
    for i, table in enumerate(tables):
        current_df = table.df.copy()

        if current_df.empty:
            continue
        
        # Clean up empty strings and leading/trailing whitespace from all cells
        current_df = current_df.apply(lambda x: x.astype(str).str.strip() if x.dtype == "object" else x)
        current_df = current_df.replace('', np.nan) # Replace empty strings with NaN

        # Robustly identify and set headers for the current table
        header_row_found = False
        potential_header_rows = []
        
        # Check the first few rows for potential headers (up to 5 rows)
        for r_idx in range(min(5, len(current_df))):
            row_values_str = ' '.join(current_df.iloc[r_idx].dropna().astype(str).tolist()).lower()
            # Heuristic: Check if key header terms are present in the row
            if all(term in row_values_str for term in ['date', 'description', 'amt', 'balance']):
                potential_header_rows.append((r_idx, current_df.iloc[r_idx].tolist()))
        
        if potential_header_rows:
            # Take the first identified header row
            header_row_index, actual_header_values = potential_header_rows[0]
            current_df.columns = actual_header_values
            current_df = current_df.iloc[header_row_index + 1:].reset_index(drop=True)
            header_row_found = True
        else:
            # Fallback: if no clear header row found in data, check if camelot assigned numerical columns
            # and the first row *is* the header.
            if all(col.isdigit() or col == '' for col in current_df.columns.astype(str)):
                # Assume the first row contains headers if columns are numerical/empty
                if not current_df.empty:
                    current_df.columns = current_df.iloc[0].tolist()
                    current_df = current_df.iloc[1:].reset_index(drop=True)
                    header_row_found = True
        
        # Ensure the DataFrame has the correct number of columns before assigning `expected_headers`
        # This handles cases where camelot might extract extra or fewer columns.
        if len(current_df.columns) > len(expected_headers):
            current_df = current_df.iloc[:, :len(expected_headers)]
        elif len(current_df.columns) < len(expected_headers):
            # Add missing columns with NaN values to match expected_headers length
            for col_idx in range(len(current_df.columns), len(expected_headers)):
                current_df[expected_headers[col_idx]] = np.nan
        
        # Always assign the `expected_headers` for consistency across all tables
        current_df.columns = expected_headers
        
        # Address "Skip column names from second page of pdf":
        # After setting columns, check if the first data row (if any) is actually a repeated header row
        # (which might happen if camelot extracts headers and we then re-assigned columns).
        if not current_df.empty:
            first_data_row_values = current_df.iloc[0].astype(str).tolist()
            # Strip whitespace from values for a more accurate comparison
            cleaned_first_row = [str(x).strip() for x in first_data_row_values]
            cleaned_expected_headers = [str(x).strip() for x in expected_headers]

            # If the first data row content is identical to the expected headers, drop it
            if cleaned_first_row == cleaned_expected_headers:
                current_df = current_df.iloc[1:].reset_index(drop=True)

        if not current_df.empty:
            all_extracted_dfs.append(current_df)

    if not all_extracted_dfs:
        parsed_df = pd.DataFrame(columns=expected_headers)
    else:
        # Concatenate all processed DataFrames into a single DataFrame
        parsed_df = pd.concat(all_extracted_dfs, ignore_index=True)

# --- Numeric Column Conversion ---
# Identify columns that should be numeric based on the sample data
numeric_cols = ['Debit Amt', 'Credit Amt', 'Balance']

for col in numeric_cols:
    if col in parsed_df.columns:
        # Ensure the column is string type before applying string operations
        # Remove non-numeric characters (except digits, dot, and hyphen for negative numbers)
        # using a regex to handle various currency symbols, commas, spaces etc.
        parsed_df[col] = parsed_df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        # Convert to numeric, coercing any conversion errors to NaN (Not a Number)
        parsed_df[col] = pd.to_numeric(parsed_df[col], errors='coerce')

# --- Save to CSV ---
# Save the final DataFrame to the specified CSV path without including the DataFrame index
parsed_df.to_csv(output_csv_path, index=False)
