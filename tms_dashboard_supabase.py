# -*- coding: utf-8 -*-
"""
Created on Mon Oct 27 13:43:32 2025

@author: aroma
"""

import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import streamlit as st
import streamlit_authenticator as stauth
import toml

# --- Load config and set up authenticator ---
config = toml.load("config.toml") 
# Load config from Streamlit secrets for cloud deployment
#config = dict(st.secrets)

#config["credentials"] = dict(config["credentials"])
#config["cookie"] = dict(config["cookie"])

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"]
)

# --- Login UI ---
authenticator.login()

auth_status = st.session_state.get("authentication_status")

if auth_status is None:
    st.warning("⚠️ Please log in to continue.")
    st.stop()  # 🚧 Stop execution here — nothing below is run or displayed

elif auth_status is False:
    st.error("❌ Username or password incorrect.")
    st.stop()

# --- If we reached here, user is authenticated ---
authenticator.logout(location="sidebar")
st.sidebar.markdown(f"👋 Logged in as: **{st.session_state['name']}**")


# ==================== HELPER: TYPE CONVERSION ====================

def convert_numpy_types(value):
    """Convert numpy types to Python native types for psycopg2"""
    if isinstance(value, np.integer):
        return int(value)
    elif isinstance(value, np.floating):
        return float(value)
    elif isinstance(value, np.ndarray):
        return value.tolist()
    return value

# ==================== DATABASE FUNCTIONS ====================

@st.cache_resource
def init_database():
    """Initialize PostgreSQL connection to Supabase"""
    try:
        conn = psycopg2.connect(
            host=st.secrets["DB_HOST"],
            port=st.secrets["DB_PORT"],
            database=st.secrets["DB_NAME"],
            user=st.secrets["DB_USER"],
            password=st.secrets["DB_PASSWORD"]
        )
        conn.autocommit = False
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        st.stop()

# Initialize connection
if 'db_conn' not in st.session_state:
    st.session_state.db_conn = init_database()
conn = st.session_state.db_conn

def get_cursor():
    """Get a fresh cursor from the connection"""
    try:
        return conn.cursor()
    except Exception as e:
        conn.rollback()
        return conn.cursor()

def execute_query(query, params=None, fetch_one=False, fetch_all=True):
    """Execute SELECT queries safely"""
    try:
        c = get_cursor()
        if params:
            # Convert numpy types in params
            params = tuple(convert_numpy_types(p) for p in params)
            c.execute(query, params)
        else:
            c.execute(query)
        if fetch_one:
            result = c.fetchone()
        elif fetch_all:
            result = c.fetchall()
        else:
            result = None
        c.close()
        return result
    except Exception as e:
        conn.rollback()
        st.error(f"Query error: {e}")
        return None

def execute_update(query, params=None):
    """Execute INSERT/UPDATE/DELETE queries safely"""
    try:
        c = get_cursor()
        if params:
            # Convert numpy types in params
            params = tuple(convert_numpy_types(p) for p in params)
            c.execute(query, params)
        else:
            c.execute(query)
        conn.commit()
        c.close()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Update error: {e}")
        return False

def execute_insert_with_return(query, params=None):
    """Execute INSERT and return the last inserted ID"""
    try:
        c = get_cursor()
        if params:
            # Convert numpy types in params
            params = tuple(convert_numpy_types(p) for p in params)
            c.execute(query, params)
        else:
            c.execute(query)
        result = c.fetchone()[0] if c.description else None
        conn.commit()
        c.close()
        return int(result) if result else None
    except Exception as e:
        conn.rollback()
        st.error(f"Insert error: {e}")
        return None

def create_tables():
    """Create all required tables"""
    try:
        c = get_cursor()

        # Patients table
        c.execute("""CREATE TABLE IF NOT EXISTS patients
        (id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        mrn TEXT UNIQUE NOT NULL,
        age INTEGER,
        gender TEXT,
        primary_diagnosis TEXT,
        tass_completed INTEGER DEFAULT 0,
        consent_obtained INTEGER DEFAULT 0,
        referred_date DATE,
        status TEXT DEFAULT 'Pending Review')""")

        # Protocol Library table
        c.execute("""CREATE TABLE IF NOT EXISTS protocol_library
        (id SERIAL PRIMARY KEY,
        protocol_name TEXT UNIQUE NOT NULL,
        waveform_type TEXT,
        burst_pulses INTEGER,
        inter_pulse_interval REAL,
        pulse_rate REAL,
        pulses_per_train INTEGER,
        num_trains INTEGER,
        inter_train_interval REAL,
        session_duration INTEGER)""")

        # TMS Sessions table
        c.execute("""CREATE TABLE IF NOT EXISTS tms_sessions
        (id SERIAL PRIMARY KEY,
        patient_id INTEGER,
        session_number INTEGER,
        session_date DATE,
        protocol_id INTEGER,
        target_laterality TEXT,
        target_region TEXT,
        coord_left_x REAL,
        coord_left_y REAL,
        coord_right_x REAL,
        coord_right_y REAL,
        rmt_left REAL,
        rmt_right REAL,
        intensity_percent_left REAL,
        intensity_percent_right REAL,
        intensity_output_left INTEGER,
        intensity_output_right INTEGER,
        coil_type TEXT,
        side_effects TEXT,
        remarks TEXT,
        status TEXT DEFAULT 'Pending',
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
        FOREIGN KEY (protocol_id) REFERENCES protocol_library(id) ON DELETE SET NULL)""")

        # Daily Slots table
        c.execute("""CREATE TABLE IF NOT EXISTS daily_slots
        (id SERIAL PRIMARY KEY,
        slot_date DATE,
        session_id INTEGER,
        scheduled_time TEXT,
        slot_duration INTEGER,
        status TEXT DEFAULT 'Scheduled',
        sr_name TEXT,
        jr1_name TEXT,
        jr2_name TEXT,
        FOREIGN KEY (session_id) REFERENCES tms_sessions(id) ON DELETE CASCADE)""")

        # Holiday Calendar table
        c.execute("""CREATE TABLE IF NOT EXISTS holidays
        (id SERIAL PRIMARY KEY,
        holiday_date DATE UNIQUE,
        holiday_name TEXT,
        skip_enabled INTEGER DEFAULT 1)""")

        conn.commit()
        c.close()
        return True
    except Exception as e:
        conn.rollback()
        return False

# Initialize database tables
create_tables()

# ==================== PAGE CONFIGURATION ====================

st.set_page_config(page_title="TMS Dashboard", layout="wide", initial_sidebar_state="expanded")

# Sidebar navigation
st.sidebar.title("🏥 TMS Dashboard")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navigation",
    ["📊 Daily Dashboard",
     "👤 Patient Referral",
     "🗓️ Slot Management",
     "📝 Session Parameters",
     "📚 Protocol Library",
     "🎯 Holiday Calendar"])

# ==================== HELPER FUNCTIONS ====================

def get_protocols():
    """Fetch all protocols from database"""
    try:
        results = execute_query("SELECT id, protocol_name, waveform_type, session_duration FROM protocol_library ORDER BY protocol_name")
        if results:
            return pd.DataFrame(results, columns=['id', 'protocol_name', 'waveform_type', 'session_duration'])
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching protocols: {e}")
        return pd.DataFrame()

def get_patients():
    """Fetch all patients from database"""
    try:
        results = execute_query("SELECT id, name, mrn, age, gender, primary_diagnosis, status FROM patients ORDER BY referred_date DESC")
        if results:
            return pd.DataFrame(results, columns=['id', 'name', 'mrn', 'age', 'gender', 'primary_diagnosis', 'status'])
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching patients: {e}")
        return pd.DataFrame()

def get_sessions_for_patient(patient_id):
    """Fetch all sessions for a patient"""
    try:
        # Convert numpy type to int
        patient_id = convert_numpy_types(patient_id)
        results = execute_query(
            """SELECT id, session_number, session_date, status FROM tms_sessions 
               WHERE patient_id = %s ORDER BY session_number DESC""",
            (patient_id,)
        )
        if results:
            return pd.DataFrame(results, columns=['id', 'session_number', 'session_date', 'status'])
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching sessions: {e}")
        return pd.DataFrame()

def calculate_intensity(percent_rmt, rmt_value):
    """Calculate intensity output from RMT percentage"""
    if rmt_value and percent_rmt:
        return int((percent_rmt / 100) * rmt_value)
    return None

def get_next_session_number(patient_id):
    """Get next session number for a patient"""
    try:
        patient_id = convert_numpy_types(patient_id)
        result = execute_query("SELECT MAX(session_number) FROM tms_sessions WHERE patient_id = %s", (patient_id,), fetch_one=True)
        if result and result[0]:
            return int(result[0]) + 1
        return 1
    except Exception as e:
        st.error(f"Error getting session number: {e}")
        return 1

def is_holiday(date):
    """Check if a date is a holiday"""
    try:
        result = execute_query("SELECT id FROM holidays WHERE holiday_date = %s AND skip_enabled = 1", (date,), fetch_one=True)
        return result is not None
    except Exception as e:
        return False

def get_previous_session_data(patient_id):
    """Get previous session data for auto-population"""
    try:
        patient_id = convert_numpy_types(patient_id)
        query = """SELECT ts.*, pl.protocol_name FROM tms_sessions ts
        LEFT JOIN protocol_library pl ON ts.protocol_id = pl.id
        WHERE ts.patient_id = %s ORDER BY ts.session_number DESC LIMIT 1"""
        result = execute_query(query, (patient_id,), fetch_one=True)
        if result:
            return result
        return None
    except Exception as e:
        return None

# ==================== DELETE FUNCTIONS ====================

def delete_session(session_id):
    """Delete a session and its associated slot"""
    try:
        # Convert numpy type to int
        session_id = convert_numpy_types(session_id)

        # Delete associated slot first
        execute_update("DELETE FROM daily_slots WHERE session_id = %s", (session_id,))
        # Delete session
        execute_update("DELETE FROM tms_sessions WHERE id = %s", (session_id,))
        return True
    except Exception as e:
        st.error(f"Error deleting session: {e}")
        return False

def delete_patient(patient_id):
    """Delete a patient and all associated records"""
    try:
        # Convert numpy type to int
        patient_id = convert_numpy_types(patient_id)

        # This will cascade delete all sessions and slots due to foreign keys
        execute_update("DELETE FROM patients WHERE id = %s", (patient_id,))
        return True
    except Exception as e:
        st.error(f"Error deleting patient: {e}")
        return False

# ==================== PAGE 1: DAILY DASHBOARD ====================

if page == "📊 Daily Dashboard":
    st.markdown("## 📊 TMS Daily Dashboard")

    # Date selector
    selected_date = st.date_input("Select Date", datetime.now())

    col1, col2, col3 = st.columns(3)

    # Staff assignment
    with col1:
        st.markdown("### 👨⚕️ Staff Assignment")
        sr_name = st.text_input("Senior Resident", key="sr_daily")
        jr1_name = st.text_input("Junior Resident 1", key="jr1_daily")
        jr2_name = st.text_input("Junior Resident 2", key="jr2_daily")

        if st.button("Save Staff Assignment"):
            if execute_update(
                """UPDATE daily_slots SET sr_name = %s, jr1_name = %s, jr2_name = %s
                WHERE slot_date = %s""",
                (sr_name, jr1_name, jr2_name, selected_date)
            ):
                st.success("✅ Staff assignment saved!")

    # Slot capacity info
    with col2:
        st.markdown("### 📊 Capacity Info")
        st.metric("Maximum Daily Slots", "20")
        st.metric("Concurrent Operations", "2")

        # Count today's slots
        result = execute_query("SELECT COUNT(*) FROM daily_slots WHERE slot_date = %s", (selected_date,), fetch_one=True)
        current_slots = int(result[0]) if result else 0
        st.metric("Slots Scheduled Today", current_slots)

    with col3:
        st.markdown("### 📈 Session Statistics")
        results = execute_query(
            """SELECT status, COUNT(*) as count FROM daily_slots
            WHERE slot_date = %s GROUP BY status""",
            (selected_date,)
        )

        if results:
            for status, count in results:
                st.metric(status, int(count))

    # Today's schedule
    st.markdown("### 📅 Today's Schedule")

    results = execute_query(
        """SELECT p.name as patient_name, ts.session_number, pl.protocol_name,
        COALESCE(ts.target_laterality || ' ' || ts.target_region, 'N/A') as target,
        ds.scheduled_time, ds.status, ds.slot_duration, ds.id as slot_id, ts.id as session_id
        FROM daily_slots ds
        JOIN tms_sessions ts ON ds.session_id = ts.id
        JOIN patients p ON ts.patient_id = p.id
        LEFT JOIN protocol_library pl ON ts.protocol_id = pl.id
        WHERE ds.slot_date = %s
        ORDER BY ds.scheduled_time""",
        (selected_date,)
    )

    if results:
        df = pd.DataFrame(results, columns=['Patient', 'Session', 'Protocol', 'Target', 'Time', 'Status', 'Duration', 'slot_id', 'session_id'])

        # Display without action columns
        display_df = df[['Patient', 'Session', 'Protocol', 'Target', 'Time', 'Status', 'Duration']]
        st.dataframe(display_df, use_container_width=True)

        # Delete session from schedule
        st.markdown("### 🗑️ Remove Session from Schedule")
        session_options = [f"Session {row['Session']} - {row['Patient']}" for _, row in df.iterrows()]
        selected_session = st.selectbox("Select session to remove", session_options)

        if st.button("Remove Selected Session", type="secondary"):
            selected_idx = session_options.index(selected_session)
            session_id = int(df.iloc[selected_idx]['session_id'])  # Explicit int conversion

            if delete_session(session_id):
                st.success("✅ Session removed from schedule!")
                st.rerun()
    else:
        st.info("ℹ️ No sessions scheduled for this date")

# ==================== PAGE 2: PATIENT REFERRAL ====================

elif page == "👤 Patient Referral":
    st.markdown("## 👤 Patient Referral")

    st.markdown("### 📋 Patient Information")

    col1, col2 = st.columns(2)

    with col1:
        patient_name = st.text_input("Patient Name *")
        mrn = st.text_input("MRN (Medical Record Number) *")
        age = st.number_input("Age", min_value=18, max_value=100, value=40)
        gender = st.selectbox("Gender", ["Male", "Female", "Other"])

    with col2:
        primary_diagnosis = st.text_area("Primary Diagnosis *", height=80)
        tass_completed = st.checkbox("TASS Checklist Completed *")
        consent_obtained = st.checkbox("TMS Consent Form Obtained *")

    if st.button("Submit Referral", type="primary"):
        if not (patient_name and mrn and primary_diagnosis):
            st.error("❌ Please fill all required fields marked with *")
        elif not (tass_completed and consent_obtained):
            st.error("❌ TASS checklist and consent form must be completed")
        else:
            if execute_update(
                """INSERT INTO patients (name, mrn, age, gender, primary_diagnosis,
                tass_completed, consent_obtained, referred_date, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (patient_name, mrn, int(age), gender, primary_diagnosis, 1, 1,
                datetime.now().date(), 'Pending Review')
            ):
                st.success("✅ Patient referral submitted successfully!")
                st.info("ℹ️ Case forwarded to NIBS team for review")

    # Display pending referrals
    st.markdown("### 📋 Pending Referrals")

    results = execute_query(
        """SELECT id, name, mrn, age, gender, primary_diagnosis, referred_date, status
        FROM patients WHERE status = 'Pending Review'
        ORDER BY referred_date DESC"""
    )

    if results:
        df = pd.DataFrame(results, columns=['ID', 'Name', 'MRN', 'Age', 'Gender', 'Diagnosis', 'Referred', 'Status'])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("ℹ️ No pending referrals")

    # Remove patient section
    st.markdown("### 🗑️ Remove Patient from System")

    patients_df = get_patients()

    if not patients_df.empty:
        st.warning("⚠️ WARNING: This will permanently delete the patient and all associated sessions and data.")

        patient_names = [f"{row['name']} (MRN: {row['mrn']})" for _, row in patients_df.iterrows()]
        selected_patient_name = st.selectbox("Select patient to remove", patient_names)

        patient_name_to_remove = selected_patient_name.split(" (MRN:")[0]
        # Convert to int explicitly
        patient_id = int(patients_df[patients_df['name'] == patient_name_to_remove]['id'].values[0])

        # Show associated sessions count
        sessions_df = get_sessions_for_patient(patient_id)
        st.info(f"ℹ️ This patient has {len(sessions_df)} scheduled/completed sessions that will also be deleted.")

        # Confirmation
        confirm_delete = st.checkbox("I confirm I want to delete this patient and all associated data")

        if st.button("Delete Patient Permanently", type="secondary", disabled=not confirm_delete):
            if delete_patient(patient_id):
                st.success("✅ Patient and all associated records deleted!")
                st.rerun()
    else:
        st.info("ℹ️ No patients in system to delete")

# ==================== PAGE 3: SLOT MANAGEMENT ====================

elif page == "🗓️ Slot Management":
    st.markdown("## 🗓️ Slot Management")

    patients_df = get_patients()

    if patients_df.empty:
        st.warning("⚠️ No patients in the system. Please add a patient referral first.")
    else:
        patient_options = {f"{row['name']} (MRN: {row['mrn']})": int(row['id'])
                          for _, row in patients_df.iterrows()}

        selected_patient = st.selectbox("Select Patient", list(patient_options.keys()))
        patient_id = patient_options[selected_patient]

        # Show existing sessions
        st.markdown("### 📋 Existing Sessions")

        sessions_df = get_sessions_for_patient(patient_id)

        if not sessions_df.empty:
            st.dataframe(sessions_df, use_container_width=True)

            # Delete session option
            st.markdown("### 🗑️ Delete Session from List")

            session_options = [f"Session #{row['session_number']} ({row['session_date']})" 
                             for _, row in sessions_df.iterrows()]

            selected_session = st.selectbox("Select session to delete", session_options)

            if st.button("Delete Selected Session", type="secondary"):
                selected_idx = session_options.index(selected_session)
                session_id = int(sessions_df.iloc[selected_idx]['id'])  # Explicit int conversion

                if delete_session(session_id):
                    st.success("✅ Session deleted successfully!")
                    st.rerun()

        # Add new sessions
        st.markdown("### ➕ Add New Sessions")

        col1, col2 = st.columns(2)

        with col1:
            slot_type = st.radio("Session Type", ["Bulk Sessions", "Single Session"])
            start_date = st.date_input("Start Date", datetime.now())

        with col2:
            if slot_type == "Bulk Sessions":
                num_sessions = st.number_input("Number of Sessions", min_value=1, max_value=50, value=14)
            else:
                num_sessions = 1

        protocols_df = get_protocols()

        if not protocols_df.empty:
            protocol_options = {row['protocol_name']: int(row['id'])
                              for _, row in protocols_df.iterrows()}

            selected_protocol = st.selectbox("Protocol", list(protocol_options.keys()))
            protocol_id = protocol_options[selected_protocol]
        else:
            st.warning("⚠️ No protocols configured. Please add protocols first.")
            protocol_id = None

        if st.button("Create Slots", type="primary") and protocol_id:
            current_date = start_date
            session_num = get_next_session_number(patient_id)
            created_count = 0

            # Get protocol duration
            proto_result = execute_query(
                "SELECT session_duration FROM protocol_library WHERE id = %s",
                (protocol_id,),
                fetch_one=True
            )

            base_duration = int(proto_result[0]) if proto_result else 20

            for _ in range(num_sessions):
                # Skip Sundays and holidays
                while current_date.weekday() == 6 or is_holiday(current_date):
                    current_date += timedelta(days=1)

                # Add 15 min for first session
                duration = base_duration + 15 if session_num == 1 else base_duration

                # Create session with RETURNING clause
                session_id = execute_insert_with_return(
                    """INSERT INTO tms_sessions
                    (patient_id, session_number, session_date, protocol_id, status)
                    VALUES (%s, %s, %s, %s, 'Scheduled') RETURNING id""",
                    (patient_id, int(session_num), current_date, protocol_id)
                )

                if session_id:
                    # Create slot
                    execute_update(
                        """INSERT INTO daily_slots
                        (slot_date, session_id, scheduled_time, slot_duration, status)
                        VALUES (%s, %s, %s, %s, 'Scheduled')""",
                        (current_date, int(session_id), "09:00", int(duration))
                    )

                    created_count += 1
                    session_num += 1

                current_date += timedelta(days=1)

            st.success(f"✅ Created {created_count} session slots successfully!")
            st.info("ℹ️ Sundays and holidays were automatically skipped")

# ==================== PAGE 4: SESSION PARAMETERS ====================

elif page == "📝 Session Parameters":
    st.markdown("## 📝 Session Parameters")

    patients_df = get_patients()

    if patients_df.empty:
        st.warning("⚠️ No patients in the system")
    else:
        patient_options = {f"{row['name']} (MRN: {row['mrn']})": int(row['id'])
                          for _, row in patients_df.iterrows()}

        selected_patient = st.selectbox("Select Patient", list(patient_options.keys()), key="param_patient")
        patient_id = patient_options[selected_patient]

        # Get today's session
        today = datetime.now().date()
        results = execute_query(
            """SELECT id, session_number, protocol_id FROM tms_sessions
            WHERE patient_id = %s AND session_date = %s AND status = 'Scheduled'""",
            (patient_id, today)
        )

        if not results:
            st.info("ℹ️ No scheduled session for today for this patient")
        else:
            session_id, session_num, protocol_id = results[0]
            session_id = int(session_id)
            session_num = int(session_num)
            protocol_id = int(protocol_id) if protocol_id else None

            st.markdown(f"### Session #{session_num}")

            # Get previous session data
            prev_session = get_previous_session_data(patient_id)

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Protocol & Target")

                protocols_df = get_protocols()
                protocol_options = {row['protocol_name']: int(row['id'])
                                  for _, row in protocols_df.iterrows()}

                selected_protocol = st.selectbox("Protocol Name", list(protocol_options.keys()))

                laterality = st.selectbox("Target Laterality", ["Left", "Right", "Bilateral"])

                target_region = st.text_input("Brain Region (e.g., DLPFC, IFG, PMC)", value="")

                coil_type = st.selectbox("Coil Type",
                    ["rTMS (figure-8 coil)", "rTMS (double cone)",
                     "H1 (deep TMS)", "H4 (deep TMS)", "H7 (deep TMS)"])

            with col2:
                st.subheader("Coordinates (2D)")

                coord_left_x = st.number_input("Left X (from outer canthus, cm)", value=0.0, step=0.1)
                coord_left_y = st.number_input("Left Y (from tragus, cm)", value=0.0, step=0.1)
                coord_right_x = st.number_input("Right X (from outer canthus, cm)", value=0.0, step=0.1)
                coord_right_y = st.number_input("Right Y (from tragus, cm)", value=0.0, step=0.1)

            st.markdown("---")

            col3, col4 = st.columns(2)

            with col3:
                st.subheader("Resting Motor Threshold (RMT)")

                rmt_left = st.number_input("Left RMT (%)", value=0.0, step=1.0)
                rmt_right = st.number_input("Right RMT (%)", value=0.0, step=1.0)

            with col4:
                st.subheader("Treatment Intensity")

                intensity_pct_left = st.number_input("% of RMT (Left)", value=0.0, step=1.0)
                intensity_pct_right = st.number_input("% of RMT (Right)", value=0.0, step=1.0)

                # Auto-calculate intensity output
                intensity_out_left = calculate_intensity(intensity_pct_left, rmt_left)
                intensity_out_right = calculate_intensity(intensity_pct_right, rmt_right)

                st.metric("Intensity Output (Left)", f"{intensity_out_left}" if intensity_out_left else "-")
                st.metric("Intensity Output (Right)", f"{intensity_out_right}" if intensity_out_right else "-")

            st.markdown("---")

            st.subheader("Session Notes")

            side_effects = st.text_area("Side Effects", height=100)
            remarks = st.text_area("Remarks", height=100)

            if st.button("Complete Session", type="primary"):
                if execute_update(
                    """UPDATE tms_sessions
                    SET target_laterality = %s, target_region = %s,
                    coord_left_x = %s, coord_left_y = %s,
                    coord_right_x = %s, coord_right_y = %s,
                    rmt_left = %s, rmt_right = %s,
                    intensity_percent_left = %s, intensity_percent_right = %s,
                    intensity_output_left = %s, intensity_output_right = %s,
                    coil_type = %s, side_effects = %s, remarks = %s,
                    status = 'Completed'
                    WHERE id = %s""",
                    (laterality, target_region, float(coord_left_x), float(coord_left_y),
                     float(coord_right_x), float(coord_right_y), float(rmt_left), float(rmt_right),
                     float(intensity_pct_left), float(intensity_pct_right),
                     int(intensity_out_left) if intensity_out_left else None,
                     int(intensity_out_right) if intensity_out_right else None,
                     coil_type, side_effects, remarks, int(session_id))
                ):
                    # Update slot status
                    execute_update(
                        "UPDATE daily_slots SET status = 'Completed' WHERE session_id = %s",
                        (int(session_id),)
                    )

                    st.success("✅ Session completed successfully!")

# ==================== PAGE 5: PROTOCOL LIBRARY ====================

elif page == "📚 Protocol Library":
    st.markdown("## 📚 Protocol Library")

    tab1, tab2 = st.tabs(["View Protocols", "Add New Protocol"])

    with tab1:
        st.markdown("### Existing Protocols")

        protocols_df = get_protocols()

        if not protocols_df.empty:
            st.dataframe(protocols_df, use_container_width=True)

            # Delete protocol
            st.markdown("### 🗑️ Delete Protocol")

            delete_protocol = st.selectbox("Select protocol to delete",
                protocols_df['protocol_name'].tolist())

            if st.button("Delete Selected Protocol", type="secondary"):
                if execute_update(
                    "DELETE FROM protocol_library WHERE protocol_name = %s",
                    (delete_protocol,)
                ):
                    st.success(f"✅ Protocol '{delete_protocol}' deleted!")
                    st.rerun()
        else:
            st.info("ℹ️ No protocols configured yet")

    with tab2:
        st.markdown("### Add New Protocol")

        col1, col2 = st.columns(2)

        with col1:
            protocol_name = st.text_input("Protocol Name *")
            waveform_type = st.selectbox("Waveform Type", ["Biphasic", "Biphasic Bursts"])

            if waveform_type == "Biphasic Bursts":
                burst_pulses = st.number_input("Burst Pulses", min_value=1, value=3)
                inter_pulse_interval = st.number_input("Inter-pulse Interval (ms)", value=20.0)
            else:
                burst_pulses = None
                inter_pulse_interval = None

            pulse_rate = st.number_input("Pulse/Burst Rate (Hz)", value=1.0, step=0.1)

        with col2:
            pulses_per_train = st.number_input("Pulses/Bursts per Train", min_value=1, value=10)
            num_trains = st.number_input("Number of Trains", min_value=1, value=20)
            inter_train_interval = st.number_input("Inter-train Interval (seconds)", value=8.0, step=0.5)
            session_duration = st.number_input("Session Duration (minutes)", min_value=1, value=5)

        if st.button("Add Protocol", type="primary"):
            if not protocol_name:
                st.error("❌ Protocol name is required")
            else:
                if execute_update(
                    """INSERT INTO protocol_library
                    (protocol_name, waveform_type, burst_pulses, inter_pulse_interval,
                    pulse_rate, pulses_per_train, num_trains, inter_train_interval, session_duration)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (protocol_name, waveform_type, int(burst_pulses) if burst_pulses else None,
                     float(inter_pulse_interval) if inter_pulse_interval else None,
                     float(pulse_rate), int(pulses_per_train), int(num_trains),
                     float(inter_train_interval), int(session_duration))
                ):
                    st.success("✅ Protocol added successfully!")

# ==================== PAGE 6: HOLIDAY CALENDAR ====================

elif page == "🎯 Holiday Calendar":
    st.markdown("## 🎯 Holiday Calendar")

    tab1, tab2 = st.tabs(["View Holidays", "Add Holiday"])

    with tab1:
        st.markdown("### Configured Holidays")

        results = execute_query("SELECT id, holiday_date, holiday_name, skip_enabled FROM holidays ORDER BY holiday_date")

        if results:
            df = pd.DataFrame(results, columns=['ID', 'Date', 'Holiday Name', 'Skip Enabled'])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("ℹ️ No holidays configured")

    with tab2:
        st.markdown("### Add New Holiday")

        holiday_date = st.date_input("Holiday Date")
        holiday_name = st.text_input("Holiday Name")
        skip_enabled = st.checkbox("Enable Auto-skip", value=True)

        if st.button("Add Holiday", type="primary"):
            if not holiday_name:
                st.error("❌ Holiday name is required")
            else:
                if execute_update(
                    """INSERT INTO holidays (holiday_date, holiday_name, skip_enabled)
                    VALUES (%s, %s, %s)""",
                    (holiday_date, holiday_name, 1 if skip_enabled else 0)
                ):
                    st.success("✅ Holiday added successfully!")

# Footer
st.sidebar.markdown("---")
st.sidebar.info("💡 TMS Integration Dashboard v2.2 (Type conversion fix applied)")

