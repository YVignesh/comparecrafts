import streamlit as st
import pandas as pd
from io import BytesIO
import json
import re

def process_key(df, key_columns, case_sensitive):
    key_parts = df[key_columns].astype(str)

    if not case_sensitive:
        key_parts = key_parts.applymap(lambda x: x.lower())

    return key_parts.agg('|'.join, axis=1)

def build_filter_ui(df, label_prefix, saved_filters=None):
    st.markdown(f"##### 🔍 {label_prefix} Filter Builder (supports ==, contains, not contains, etc.)")

    filters = []
    num_default = len(saved_filters) if saved_filters else 0
    num_filters = st.number_input(f"Number of filters for {label_prefix}", min_value=0, max_value=5, value=num_default, step=1, key=f"{label_prefix}_filter_count")

    for i in range(num_filters):
        saved = saved_filters[i] if saved_filters and i < len(saved_filters) else None

        col_name = saved[0] if saved and len(saved) > 0 else None
        operator = saved[1] if saved and len(saved) > 1 else "=="
        value = saved[2] if saved and len(saved) > 2 else ""
        case_sensitive = saved[3] if saved and len(saved) > 3 else False
        use_regex = saved[4] if saved and len(saved) > 4 else False


        col = st.selectbox(
            f"Filter {i+1} column ({label_prefix})", 
            options=df.columns.tolist(), 
            #index=df.columns.get_loc(saved[0]) if saved else 0,
            index=df.columns.get_loc(saved[0]) if saved and saved[0] in df.columns else 0,
            key=f"{label_prefix}_col_{i}"
        )

        op = st.selectbox(
            f"Condition for {col}",
            options=["==", "!=", ">", ">=", "<", "<=", "contains", "not contains"],
            index=(["==", "!=", ">", ">=", "<", "<=", "contains", "not contains"].index(saved[1]) if saved else 0),
            key=f"{label_prefix}_op_{i}"
        )

        if op == "==" or op == "!=":
            val = st.selectbox(f"Value for {col}", options=sorted(df[col].dropna().astype(str).unique()), index=0 if saved and saved[2] in df[col].astype(str).tolist() else 0, key=f"{label_prefix}_val_{i}")
        else:
            val = st.text_input(f"Value for {col}", value=saved[2] if saved else "", key=f"{label_prefix}_val_{i}")

        
        case_sensitive = saved[3] if saved and len(saved) > 3 else False
        use_regex = saved[4] if saved and len(saved) > 4 else False

        if op not in ["contains", "not contains"]:
            case_sensitive = False
            use_regex = False

        if op in ["contains", "not contains"]:
            case_sensitive = st.checkbox("Case Sensitive?", value=case_sensitive, key=f"{label_prefix}_case_{i}")
            use_regex = st.checkbox("Use Regex?", value=use_regex, key=f"{label_prefix}_regex_{i}")


        filters.append((col, op, val, case_sensitive, use_regex))

    return filters

def apply_filters(df, filters):
    for f in filters:
        col, op, val, *extras = f
        case = extras[0] if len(extras) > 0 else False
        regex = extras[1] if len(extras) > 1 else False

        try:
            val_casted = pd.to_numeric(val, errors='raise')
        except:
            val_casted = val.strip()

        try:
            if op == "==":
                df = df[df[col] == val_casted]
            elif op == "!=":
                df = df[df[col] != val_casted]
            elif op == ">":
                df = df[df[col] > val_casted]
            elif op == ">=":
                df = df[df[col] >= val_casted]
            elif op == "<":
                df = df[df[col] < val_casted]
            elif op == "<=":
                df = df[df[col] <= val_casted]
            elif op == "contains":
                df = df[df[col].astype(str).str.contains(str(val_casted), na=False, case=case, regex=regex)]
            elif op == "not contains":
                df = df[~df[col].astype(str).str.contains(str(val_casted), na=False, case=case, regex=regex)]

        except Exception as e:
            st.error(f"❌ Error applying filter on column '{col}': {e}")
            st.stop()

    return df

def get_sheet_names(file):
    try:
        return pd.ExcelFile(file).sheet_names
    except Exception as e:
        st.error(f"❌ Error reading sheet names from {file.name}: {e}")
        return []

def load_data(file, sheet=None,delimiter=None):
    try:
        if file.name.endswith(".xlsx"):
            return pd.read_excel(file, sheet_name=sheet)
        elif file.name.endswith(".csv"):
            return pd.read_csv(file)
        elif file.name.endswith(".txt"):
            return pd.read_csv(file, delimiter=delimiter)
    except Exception as e:
        st.error(f"❌ Failed to load {file.name}: {e}")
        return None

def compare_df(df1, df2, case_sensitive=True):
    keys = df1.index.union(df2.index)
    columns = df1.columns.union(df2.columns)
    result = []

    for key in keys:
        if key in df1.index:
            row1 = df1.loc[key]
            if isinstance(row1, pd.DataFrame):
                row1 = row1.iloc[0]
        else:
            row1 = pd.Series([None]*len(columns), index=columns)

        if key in df2.index:
            row2 = df2.loc[key]
            if isinstance(row2, pd.DataFrame):
                row2 = row2.iloc[0]
        else:
            row2 = pd.Series([None]*len(columns), index=columns)

        diff_row = {"Key": key}
        changed = False

        for col in columns:
            val_old = row2[col] if col in row2 else None
            val_new = row1[col] if col in row1 else None

            diff_row[f"{col}_old"] = val_old
            diff_row[f"{col}_new"] = val_new

            if pd.isna(val_old) and pd.isna(val_new):
                continue
            elif pd.isna(val_old) != pd.isna(val_new) or str(val_old) != str(val_new):
                val_old_str = str(val_old) if not pd.isna(val_old) else ""
                val_new_str = str(val_new) if not pd.isna(val_new) else ""
                
                if not case_sensitive:
                    val_old_str = val_old_str.lower()
                    val_new_str = val_new_str.lower()
                
                if val_old_str != val_new_str:
                    changed = True

        if key not in df2.index:
            diff_row["ChangeType"] = "Added"
        elif key not in df1.index:
            diff_row["ChangeType"] = "Removed"
        elif changed:
            diff_row["ChangeType"] = "Modified"
        else:
            diff_row["ChangeType"] = "Unchanged"

        result.append(diff_row)

    return pd.DataFrame(result)

st.set_page_config(page_title="Kompare Krafts", layout="wide")
st.title("🔍 Kompare Krafts")

# Initialize session state for config
if "config_data" not in st.session_state:
    st.session_state.config_data = {}

# --- Load or Save Configuration ---
st.sidebar.header("🔁 Save / Load Config")
st.sidebar.markdown("""
- Use this to avoid redoing your setup for future comparisons.
- You can upload a config JSON file or generate one after comparing.
""")
config_file = st.sidebar.file_uploader("Upload Config JSON", type=["json"])
load_config = st.sidebar.button("Load Config")

if load_config and config_file:
    try:
        st.session_state.config_data = json.load(config_file)
        st.sidebar.success("✅ Config loaded!")
    except Exception as e:
        st.sidebar.error(f"❌ Failed to load config: {e}")

config_data = st.session_state.config_data
config_loaded = bool(config_data)
case_sensitive_compare = config_data.get("case_sensitive_compare", True)

#st.sidebar.json(st.session_state.config_data)

# --- File Upload ---
st.subheader("📤 Upload files")
uploaded_files = st.file_uploader("Upload two files (Excel/CSV/TXT)", type=["xlsx","csv","txt"], accept_multiple_files=True)
delimiter = st.sidebar.text_input("Delimiter (for TXT)", value="\t") if any(f.name.endswith(".txt") for f in uploaded_files or []) else None

if uploaded_files and len(uploaded_files) == 2:
    file1, file2 = uploaded_files
    file_labels = { "Main File": file1.name, "Secondary File": file2.name }

    #file_main = st.radio("Select the Main File", list(file_labels.values()), index=[file1.name, file2.name].index(config_data.get("main_excel")) if config_loaded and config_data.get("main_excel") in [file1.name, file2.name] else 0)
    st.markdown("""
        ### 📁 Select the **Main File**
        The **Main File** is treated as the primary source of truth.
        
        - Rows present in **Main File** but missing in **Secondary File** will be marked as **Added**.
        - Rows missing in **Main File** but present in **Secondary File** will be marked as **Removed**.
        - Changes are compared from **Secondary → Main**, so values in the Main File are considered the "latest" values.
        """)
    file_main = st.radio(
        "Select the Main File",
        [file1.name, file2.name],
        index=[file1.name, file2.name].index(config_data.get("main_excel")) if config_loaded and config_data.get("main_excel") in [file1.name, file2.name] else 0
    )
    file_secondary = file2.name if file_main == file1.name else file1.name
    
    # sheets_file1 = get_sheet_names(file1)
    # sheets_file2 = get_sheet_names(file2)

    # st.subheader("🧾 Sheet Selection")
    # default_main_sheet = config_data.get("main_sheet") if config_loaded else None
    # default_secondary_sheet = config_data.get("secondary_sheet") if config_loaded else None

    # sheet_main = st.selectbox(f"Select sheet from {file_main}", sheets_file1 if file_main == file1.name else sheets_file2, index=(sheets_file1 if file_main == file1.name else sheets_file2).index(default_main_sheet) if default_main_sheet in (sheets_file1 if file_main == file1.name else sheets_file2) else 0)
    # sheet_secondary = st.selectbox(f"Select sheet from {file_secondary}", sheets_file2 if file_secondary == file2.name else sheets_file1, index=(sheets_file2 if file_secondary == file2.name else sheets_file1).index(default_secondary_sheet) if default_secondary_sheet in (sheets_file2 if file_secondary == file2.name else sheets_file1) else 0)

    ################################################
    f_main = file1 if file_main == file1.name else file2
    f_secondary = file2 if file_secondary == file2.name else file1

    # --- Sheet selection if needed ---
    sheet_main = sheet_secondary = None
    if f_main.name.endswith(".xlsx"):
        sheets = get_sheet_names(f_main)
        default_main_sheet = config_data.get("main_sheet") if config_loaded else None
        sheet_main = st.selectbox(
            f"Select sheet from {file_main}", 
            sheets, 
            index=sheets.index(default_main_sheet) if default_main_sheet in sheets else 0
        )
    if f_secondary.name.endswith(".xlsx"):
        sheets = get_sheet_names(f_secondary)
        #sheet_secondary = st.selectbox(f"Select sheet from {file_secondary}", sheets)
        default_secondary_sheet = config_data.get("secondary_sheet") if config_loaded else None
        sheet_secondary = st.selectbox(
            f"Select sheet from {file_secondary}", 
            sheets, 
            index=sheets.index(default_secondary_sheet) if default_secondary_sheet in sheets else 0
        )

    ################################################

    #df_main = load_data(file1 if file_main == file1.name else file2, sheet_main)
    #df_secondary = load_data(file2 if file_secondary == file2.name else file1, sheet_secondary)
    df_main = load_data(f_main, sheet_main, delimiter)
    df_secondary = load_data(f_secondary, sheet_secondary, delimiter)
    
    # Filters
    st.subheader("🔍 Filter Conditions")
    filters_main = build_filter_ui(df_main, "Main File", config_data.get("main_filters") if config_loaded else None)
    filters_secondary = build_filter_ui(df_secondary, "Secondary File", config_data.get("secondary_filters") if config_loaded else None)

    df_main = apply_filters(df_main, filters_main)
    df_secondary = apply_filters(df_secondary, filters_secondary)

    # Column selections
    st.subheader("🧩 Select Columns for Comparison")
    default_columns_main = config_data.get("selected_columns_main") if config_loaded else []
    default_columns_secondary = config_data.get("selected_columns_secondary") if config_loaded else []

    columns_main = st.multiselect(f"Select columns from {file_main}", options=df_main.columns.tolist(), default=default_columns_main)
    columns_secondary = st.multiselect(f"Select columns from {file_secondary}", options=df_secondary.columns.tolist(), default=default_columns_secondary)

    if columns_main and columns_secondary and len(columns_main) == len(columns_secondary):
        # Column mapping
        st.subheader("🔗 Column Mapping")
        column_mapping = {}
        saved_mapping = config_data.get("column_mapping") if config_loaded else {}

        for col1, col2 in zip(columns_main, columns_secondary):
            default = saved_mapping.get(col2, col1) if config_loaded else col1
            mapped_col = st.selectbox(f"Map '{col2}' to", options=columns_main, index=columns_main.index(default) if default in columns_main else 0, key=col2)
            column_mapping[col2] = mapped_col

        # Key columns
        st.subheader("🔑 Select Key Columns (from Main File columns)")
        key_columns = st.multiselect("Select one or more columns to form synthetic key", options=columns_main, default=config_data.get("key_columns") if config_loaded else [])
        case_sensitive_compare = config_data.get("case_sensitive_compare", True)
        case_sensitive_compare = st.checkbox("🔠 Case-sensitive comparison?")
        
        if key_columns:
            df_main_cmp = df_main[columns_main].copy()
            df_secondary_cmp = df_secondary[columns_secondary].rename(columns=column_mapping)[columns_main].copy()

            df_main_cmp['__key__'] = process_key(df_main_cmp, key_columns, case_sensitive_compare)
            df_secondary_cmp['__key__'] = process_key(df_secondary_cmp, key_columns, case_sensitive_compare)

            df_main_cmp = df_main_cmp.drop_duplicates(subset="__key__", keep="first")
            df_secondary_cmp = df_secondary_cmp.drop_duplicates(subset="__key__", keep="first")
            
            df_main_cmp = df_main_cmp.set_index('__key__')
            df_secondary_cmp = df_secondary_cmp.set_index('__key__')

            #diff_report = compare_df(df_main_cmp, df_secondary_cmp).drop_duplicates(subset=["Key"])
            diff_report = compare_df(df_main_cmp, df_secondary_cmp, case_sensitive=case_sensitive_compare)

            # New: Generate summary
            summary_counts = diff_report["ChangeType"].value_counts().to_dict()
            total = len(diff_report)
            
            # Show summary
            with st.expander("📊 Difference Summary", expanded=True):
                st.markdown(f"**Total Rows Compared:** {total}")
                for k in ["Added", "Removed", "Modified", "Unchanged"]:
                    if k in summary_counts:
                        st.markdown(f"**🟢 {k}** — {summary_counts[k]} rows")
            
            # Display report
            st.subheader("📋 Difference Report")
            with st.expander("ℹ️ What does this report mean?", expanded=False):
                st.markdown("""
                    ### 📋 **Difference Report Explanation**
                    
                    Each row in the report represents a change based on the **synthetic key** you selected.
                    
                    - Columns ending with **_old** show values from the **Secondary File** (previous state).
                    - Columns ending with **_new** show values from the **Main File** (current state).
                    - **ChangeType** indicates what kind of difference was found:
                        - `Added` — Row exists only in Main File.
                        - `Removed` — Row exists only in Secondary File.
                        - `Modified` — Row exists in both but has one or more differences.
                        - `Unchanged` — Row exists in both and is identical.
                    """)
            st.dataframe(diff_report)

            def to_excel_bytes(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                return output.getvalue()

            st.download_button(
                label="📥 Download Difference Report",
                data=to_excel_bytes(diff_report),
                file_name="difference_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Save config
            comparison_config = {
            "main_excel": f_main.name,
            "main_sheet": sheet_main,
            "secondary_sheet": sheet_secondary,
            "main_filters": filters_main,
            "secondary_filters": filters_secondary,
            "selected_columns_main": columns_main,
            "selected_columns_secondary": columns_secondary,
            "column_mapping": column_mapping,
            "key_columns": key_columns,
            "case_sensitive_compare": case_sensitive_compare  # ✅ New toggle added
        }

            config_filename = st.text_input("📝 Enter config file name", value="comparison_config.json")
            safe_filename = re.sub(r'[^\w\-_. ]', '_', config_filename).strip()
            if config_filename.strip():
                st.download_button(
                    "💾 Download Comparison Config",
                    data=json.dumps(comparison_config, indent=2),
                    file_name=safe_filename if safe_filename.endswith(".json") else f"{safe_filename}.json",
                    mime="application/json")
            else:
                st.warning("⚠️ Please enter a valid config file name.")
    else:
        st.warning("Please select and map an equal number of columns from both files.")
else:
    st.info("Please upload exactly two files.")
