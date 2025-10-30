# -*- coding: utf-8 -*-
"""
Created on Mon Oct 27 13:43:32 2025

@author: aroma
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import json
import streamlit_authenticator as stauth

# Load from Streamlit secrets
authenticator = stauth.Authenticate(
    dict(st.secrets['credentials']),
    st.secrets['cookie']['name'],
    st.secrets['cookie']['key'],
    st.secrets['cookie']['expiry_days']
)

name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status == False:
    st.error('❌ Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()

# Add logout button
authenticator.logout('Logout', 'sidebar')
st.sidebar.markdown(f'Logged in as: **{name}**')


# Database setup
def init_database():
    conn = sqlite3.connect('tms_data.db', check_same_thread=False)
    c = conn.cursor()
    
    # Patients table
    c.execute('''CREATE TABLE IF NOT EXISTS patients
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  mrn TEXT UNIQUE NOT NULL,
                  age INTEGER,
                  gender TEXT,
                  primary_diagnosis TEXT,
                  tass_completed INTEGER DEFAULT 0,
                  consent_obtained INTEGER DEFAULT 0,
                  referred_date DATE,
                  status TEXT DEFAULT 'Pending Review')''')
    
    # Protocol Library table
    c.execute('''CREATE TABLE IF NOT EXISTS protocol_library
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  protocol_name TEXT UNIQUE NOT NULL,
                  waveform_type TEXT,
                  burst_pulses INTEGER,
                  inter_pulse_interval REAL,
                  pulse_rate REAL,
                  pulses_per_train INTEGER,
                  num_trains INTEGER,
                  inter_train_interval REAL,
                  session_duration INTEGER)''')
    
    # TMS Sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS tms_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                  FOREIGN KEY (patient_id) REFERENCES patients(id),
                  FOREIGN KEY (protocol_id) REFERENCES protocol_library(id))''')
    
    # Daily Slots table
    c.execute('''CREATE TABLE IF NOT EXISTS daily_slots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slot_date DATE,
                  session_id INTEGER,
                  scheduled_time TEXT,
                  slot_duration INTEGER,
                  status TEXT DEFAULT 'Scheduled',
                  sr_name TEXT,
                  jr1_name TEXT,
                  jr2_name TEXT,
                  FOREIGN KEY (session_id) REFERENCES tms_sessions(id))''')
    
    # Holiday Calendar table
    c.execute('''CREATE TABLE IF NOT EXISTS holidays
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  holiday_date DATE UNIQUE,
                  holiday_name TEXT,
                  skip_enabled INTEGER DEFAULT 1)''')
    
    conn.commit()
    return conn

# Initialize database connection
if 'conn' not in st.session_state:
    st.session_state.conn = init_database()

conn = st.session_state.conn

# Page configuration
st.set_page_config(page_title="TMS Dashboard", layout="wide", initial_sidebar_state="expanded")

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.5rem;
        margin-top: 1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

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

# Helper functions
def get_protocols():
    df = pd.read_sql_query("SELECT * FROM protocol_library", conn)
    return df

def get_patients():
    df = pd.read_sql_query("SELECT * FROM patients", conn)
    return df

def calculate_intensity(percent_rmt, rmt_value):
    if rmt_value and percent_rmt:
        return round((percent_rmt / 100) * rmt_value)
    return None

def get_next_session_number(patient_id):
    c = conn.cursor()
    c.execute("SELECT MAX(session_number) FROM tms_sessions WHERE patient_id = ?", (patient_id,))
    result = c.fetchone()[0]
    return (result + 1) if result else 1

def is_holiday(date):
    c = conn.cursor()
    c.execute("SELECT * FROM holidays WHERE holiday_date = ? AND skip_enabled = 1", (date,))
    return c.fetchone() is not None

def get_previous_session_data(patient_id):
    query = """
    SELECT ts.*, pl.protocol_name 
    FROM tms_sessions ts
    LEFT JOIN protocol_library pl ON ts.protocol_id = pl.id
    WHERE ts.patient_id = ?
    ORDER BY ts.session_number DESC
    LIMIT 1
    """
    df = pd.read_sql_query(query, conn, params=(patient_id,))
    return df.iloc[0] if not df.empty else None

# PAGE 1: DAILY DASHBOARD
if page == "📊 Daily Dashboard":
    st.markdown('<p class="main-header">📊 TMS Daily Dashboard</p>', unsafe_allow_html=True)
    
    # Date selector
    selected_date = st.date_input("Select Date", datetime.now())
    
    col1, col2, col3 = st.columns(3)
    
    # Staff assignment
    with col1:
        st.markdown('<p class="section-header">👨‍⚕️ Staff Assignment</p>', unsafe_allow_html=True)
        sr_name = st.text_input("Senior Resident", key="sr_daily")
        jr1_name = st.text_input("Junior Resident 1", key="jr1_daily")
        jr2_name = st.text_input("Junior Resident 2", key="jr2_daily")
        
        if st.button("Save Staff Assignment"):
            # Update staff for all slots on this date
            c = conn.cursor()
            c.execute("""UPDATE daily_slots 
                        SET sr_name = ?, jr1_name = ?, jr2_name = ?
                        WHERE slot_date = ?""",
                     (sr_name, jr1_name, jr2_name, selected_date))
            conn.commit()
            st.success("✅ Staff assignment saved!")
    
    # Slot capacity info
    with col2:
        st.markdown('<p class="section-header">📊 Capacity Info</p>', unsafe_allow_html=True)
        st.metric("Maximum Daily Slots", "20")
        st.metric("Concurrent Operations", "2")
        
        # Count today's slots
        query = "SELECT COUNT(*) FROM daily_slots WHERE slot_date = ?"
        c = conn.cursor()
        c.execute(query, (selected_date,))
        current_slots = c.fetchone()[0]
        st.metric("Slots Scheduled Today", current_slots)
    
    with col3:
        st.markdown('<p class="section-header">📈 Session Statistics</p>', unsafe_allow_html=True)
        # Get today's session stats
        query = """SELECT status, COUNT(*) as count 
                   FROM daily_slots 
                   WHERE slot_date = ? 
                   GROUP BY status"""
        df_stats = pd.read_sql_query(query, conn, params=(selected_date,))
        for _, row in df_stats.iterrows():
            st.metric(row['status'], row['count'])
    
    # Today's schedule
    st.markdown('<p class="section-header">📅 Today\'s Schedule</p>', unsafe_allow_html=True)
    
    query = """
    SELECT 
        p.name as patient_name,
        ts.session_number,
        pl.protocol_name,
        ts.target_laterality || ' ' || ts.target_region as target,
        ds.scheduled_time,
        ds.status,
        ds.slot_duration
    FROM daily_slots ds
    JOIN tms_sessions ts ON ds.session_id = ts.id
    JOIN patients p ON ts.patient_id = p.id
    LEFT JOIN protocol_library pl ON ts.protocol_id = pl.id
    WHERE ds.slot_date = ?
    ORDER BY ds.scheduled_time
    """
    
    df_schedule = pd.read_sql_query(query, conn, params=(selected_date,))
    
    if not df_schedule.empty:
        st.dataframe(df_schedule, use_container_width=True)
    else:
        st.info("ℹ️ No sessions scheduled for this date")

# PAGE 2: PATIENT REFERRAL
elif page == "👤 Patient Referral":
    st.markdown('<p class="main-header">👤 Patient Referral</p>', unsafe_allow_html=True)
    
    st.markdown('<p class="section-header">📋 Patient Information</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        patient_name = st.text_input("Patient Name *")
        mrn = st.text_input("MRN (Medical Record Number) *")
        age = st.number_input("Age", min_value=18, max_value=100)
        gender = st.selectbox("Gender", ["Male", "Female", "Other"])
    
    with col2:
        primary_diagnosis = st.text_area("Primary Diagnosis *")
        tass_completed = st.checkbox("TASS Checklist Completed *")
        consent_obtained = st.checkbox("TMS Consent Form Obtained *")
    
    if st.button("Submit Referral", type="primary"):
        if not (patient_name and mrn and primary_diagnosis):
            st.error("❌ Please fill all required fields marked with *")
        elif not (tass_completed and consent_obtained):
            st.error("❌ TASS checklist and consent form must be completed before referral")
        else:
            try:
                c = conn.cursor()
                c.execute("""INSERT INTO patients 
                           (name, mrn, age, gender, primary_diagnosis, 
                            tass_completed, consent_obtained, referred_date, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (patient_name, mrn, age, gender, primary_diagnosis,
                          1, 1, datetime.now().date(), 'Pending Review'))
                conn.commit()
                st.success("✅ Patient referral submitted successfully!")
                st.info("ℹ️ Case forwarded to NIBS team for review")
            except sqlite3.IntegrityError:
                st.error("❌ Patient with this MRN already exists")
    
    # Display pending referrals
    st.markdown('<p class="section-header">📋 Pending Referrals</p>', unsafe_allow_html=True)
    df_pending = pd.read_sql_query(
        "SELECT * FROM patients WHERE status = 'Pending Review' ORDER BY referred_date DESC",
        conn
    )
    if not df_pending.empty:
        st.dataframe(df_pending, use_container_width=True)
    else:
        st.info("ℹ️ No pending referrals")
    # Insert REMOVE PATIENT section here    
    st.markdown('<p class="section-header">Remove Patient (Admin)</p>', unsafe_allow_html=True)
    patients_df = get_patients()
    if not patients_df.empty:
        patient_names = [f"{row['name']} (MRN: {row['mrn']})" for _, row in patients_df.iterrows()]
        selected_patient = st.selectbox("Select patient to remove", patient_names)
        patient_id = patients_df.loc[patients_df['name'] == selected_patient.split(" (MRN:")[0], 'id'].values[0]

        password = st.text_input("Enter admin password to confirm", type="password")
        if st.button("Remove Selected Patient", type="primary"):
            if password == "123":
                c = conn.cursor()
                c.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
                # Optional: Also delete all related sessions/slots
                c.execute("DELETE FROM tms_sessions WHERE patient_id = ?", (patient_id,))
                c.execute("DELETE FROM daily_slots WHERE session_id IN (SELECT id FROM tms_sessions WHERE patient_id = ?)", (patient_id,))
                conn.commit()
                st.success(f"✅ Patient and associated records deleted!")
            else:
                st.error("❌ Incorrect password. Deletion not allowed.")
    else:
        st.info("ℹ️ No patients available to remove")
        

# PAGE 3: SLOT MANAGEMENT
elif page == "🗓️ Slot Management":
    st.markdown('<p class="main-header">🗓️ Slot Management</p>', unsafe_allow_html=True)
    
    # Patient selection
    patients_df = get_patients()
    if patients_df.empty:
        st.warning("⚠️ No patients in the system. Please add a patient referral first.")
    else:
        patient_options = {f"{row['name']} (MRN: {row['mrn']})": row['id'] 
                          for _, row in patients_df.iterrows()}
        
        selected_patient = st.selectbox("Select Patient", list(patient_options.keys()))
        patient_id = patient_options[selected_patient]
        
        # Slot creation options
        st.markdown('<p class="section-header">➕ Add Sessions</p>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            slot_type = st.radio("Session Type", ["Bulk Sessions", "Single Session"])
            start_date = st.date_input("Start Date", datetime.now())
            
        with col2:
            if slot_type == "Bulk Sessions":
                num_sessions = st.number_input("Number of Sessions", min_value=1, max_value=50, value=14)
            
            protocol_df = get_protocols()
            if not protocol_df.empty:
                protocol_options = {row['protocol_name']: row['id'] 
                                   for _, row in protocol_df.iterrows()}
                selected_protocol = st.selectbox("Protocol", list(protocol_options.keys()))
                protocol_id = protocol_options[selected_protocol]
            else:
                st.warning("⚠️ No protocols configured. Please add protocols first.")
                protocol_id = None
        
        if st.button("Create Slots", type="primary") and protocol_id:
            sessions_to_create = num_sessions if slot_type == "Bulk Sessions" else 1
            current_date = start_date
            session_num = get_next_session_number(patient_id)
            created_count = 0
            
            c = conn.cursor()
            
            # Get protocol duration
            c.execute("SELECT session_duration FROM protocol_library WHERE id = ?", (protocol_id,))
            base_duration = c.fetchone()[0]
            
            while created_count < sessions_to_create:
                # Skip Sundays and holidays
                if current_date.weekday() == 6 or is_holiday(current_date):
                    current_date += timedelta(days=1)
                    continue
                
                # Add 15 min for first session (RMT determination)
                duration = base_duration + 15 if session_num == 1 else base_duration
                
                # Create session
                c.execute("""INSERT INTO tms_sessions 
                           (patient_id, session_number, session_date, protocol_id, status)
                           VALUES (?, ?, ?, ?, 'Scheduled')""",
                         (patient_id, session_num, current_date, protocol_id))
                session_id = c.lastrowid
                
                # Create slot (simplified - start at 9 AM)
                slot_time = "09:00"
                c.execute("""INSERT INTO daily_slots 
                           (slot_date, session_id, scheduled_time, slot_duration, status)
                           VALUES (?, ?, ?, ?, 'Scheduled')""",
                         (current_date, session_id, slot_time, duration))
                
                conn.commit()
                created_count += 1
                session_num += 1
                current_date += timedelta(days=1)
            
            st.success(f"✅ Created {created_count} session slots successfully!")
            st.info("ℹ️ Sundays and holidays were automatically skipped")

# PAGE 4: SESSION PARAMETERS
elif page == "📝 Session Parameters":
    st.markdown('<p class="main-header">📝 Session Parameters</p>', unsafe_allow_html=True)
    
    # Patient and session selection
    patients_df = get_patients()
    if patients_df.empty:
        st.warning("⚠️ No patients in the system")
    else:
        patient_options = {f"{row['name']} (MRN: {row['mrn']})": row['id'] 
                          for _, row in patients_df.iterrows()}
        
        selected_patient = st.selectbox("Select Patient", list(patient_options.keys()), key="param_patient")
        patient_id = patient_options[selected_patient]
        
        # Get today's session if exists
        today = datetime.now().date()
        query = """SELECT * FROM tms_sessions 
                   WHERE patient_id = ? AND session_date = ? AND status = 'Scheduled'"""
        df_today = pd.read_sql_query(query, conn, params=(patient_id, today))
        
        if df_today.empty:
            st.info("ℹ️ No scheduled session for today for this patient")
        else:
            session = df_today.iloc[0]
            session_id = session['id']
            
            st.markdown(f'<p class="section-header">Session #{session["session_number"]}</p>', 
                       unsafe_allow_html=True)
            
            # Auto-populate from previous session
            prev_session = get_previous_session_data(patient_id)
            
            # Session Parameters Form
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Protocol & Target")
                
                protocol_df = get_protocols()
                protocol_options = {row['protocol_name']: row['id'] 
                                   for _, row in protocol_df.iterrows()}
                
                default_protocol = None
                if prev_session is not None and prev_session['protocol_name']:
                    default_idx = list(protocol_options.keys()).index(prev_session['protocol_name'])
                    selected_protocol = st.selectbox("Protocol Name", 
                                                     list(protocol_options.keys()),
                                                     index=default_idx)
                else:
                    selected_protocol = st.selectbox("Protocol Name", 
                                                     list(protocol_options.keys()))
                
                protocol_id = protocol_options[selected_protocol]
                
                laterality = st.selectbox("Target Laterality", 
                                         ["Left", "Right", "Bilateral"],
                                         index=0 if prev_session is None else 
                                         ["Left", "Right", "Bilateral"].index(prev_session['target_laterality']) 
                                         if prev_session['target_laterality'] else 0)
                
                target_region = st.text_input("Brain Region (e.g., DLPFC, IFG, PMC)", 
                                             value=prev_session['target_region'] if prev_session is not None and prev_session['target_region'] else "")
                
                coil_type = st.selectbox("Coil Type",
                                        ["rTMS (figure-8 coil)", "rTMS (double cone)", 
                                         "H1 (deep TMS)", "H4 (deep TMS)", "H7 (deep TMS)"],
                                        index=0 if prev_session is None else 
                                        ["rTMS (figure-8 coil)", "rTMS (double cone)", 
                                         "H1 (deep TMS)", "H4 (deep TMS)", "H7 (deep TMS)"].index(prev_session['coil_type'])
                                        if prev_session['coil_type'] else 0)
            
            with col2:
                st.subheader("Coordinates (2D)")
                
                coord_left_x = st.number_input("Left X (from outer canthus, cm)",
                                              value=float(prev_session['coord_left_x']) if prev_session is not None and prev_session['coord_left_x'] else 0.0,
                                              step=0.1)
                coord_left_y = st.number_input("Left Y (from tragus, cm)",
                                              value=float(prev_session['coord_left_y']) if prev_session is not None and prev_session['coord_left_y'] else 0.0,
                                              step=0.1)
                coord_right_x = st.number_input("Right X (from outer canthus, cm)",
                                               value=float(prev_session['coord_right_x']) if prev_session is not None and prev_session['coord_right_x'] else 0.0,
                                               step=0.1)
                coord_right_y = st.number_input("Right Y (from tragus, cm)",
                                               value=float(prev_session['coord_right_y']) if prev_session is not None and prev_session['coord_right_y'] else 0.0,
                                               step=0.1)
            
            st.markdown("---")
            
            col3, col4 = st.columns(2)
            
            with col3:
                st.subheader("Resting Motor Threshold (RMT)")
                
                rmt_left = st.number_input("Left RMT (%)",
                                          value=float(prev_session['rmt_left']) if prev_session is not None and prev_session['rmt_left'] else 0.0,
                                          step=1.0)
                rmt_right = st.number_input("Right RMT (%)",
                                           value=float(prev_session['rmt_right']) if prev_session is not None and prev_session['rmt_right'] else 0.0,
                                           step=1.0)
            
            with col4:
                st.subheader("Treatment Intensity")
                
                intensity_pct_left = st.number_input("% of RMT (Left)",
                                                    value=float(prev_session['intensity_percent_left']) if prev_session is not None and prev_session['intensity_percent_left'] else 0.0,
                                                    step=1.0)
                intensity_pct_right = st.number_input("% of RMT (Right)",
                                                     value=float(prev_session['intensity_percent_right']) if prev_session is not None and prev_session['intensity_percent_right'] else 0.0,
                                                     step=1.0)
                
                # Auto-calculate intensity output
                intensity_out_left = calculate_intensity(intensity_pct_left, rmt_left)
                intensity_out_right = calculate_intensity(intensity_pct_right, rmt_right)
                
                st.metric("Intensity Output (Left)", f"{intensity_out_left}" if intensity_out_left else "-")
                st.metric("Intensity Output (Right)", f"{intensity_out_right}" if intensity_out_right else "-")
            
            st.markdown("---")
            
            # Manual entry fields
            st.subheader("Session Notes (Manual Entry)")
            side_effects = st.text_area("Side Effects", height=100)
            remarks = st.text_area("Remarks (completion status, technical issues, etc.)", height=100)
            
            # Save button
            if st.button("Complete Session", type="primary"):
                c = conn.cursor()
                c.execute("""UPDATE tms_sessions 
                           SET protocol_id = ?, target_laterality = ?, target_region = ?,
                               coord_left_x = ?, coord_left_y = ?, coord_right_x = ?, coord_right_y = ?,
                               rmt_left = ?, rmt_right = ?,
                               intensity_percent_left = ?, intensity_percent_right = ?,
                               intensity_output_left = ?, intensity_output_right = ?,
                               coil_type = ?, side_effects = ?, remarks = ?, status = 'Completed'
                           WHERE id = ?""",
                         (protocol_id, laterality, target_region,
                          coord_left_x, coord_left_y, coord_right_x, coord_right_y,
                          rmt_left, rmt_right,
                          intensity_pct_left, intensity_pct_right,
                          intensity_out_left, intensity_out_right,
                          coil_type, side_effects, remarks, session_id))
                
                # Update slot status
                st.info(f"Updating slot status for session_id: {session_id}")
                c.execute("""UPDATE daily_slots SET status = 'Completed' 
                           WHERE session_id = ?""", (session_id,))
                
                conn.commit()
                st.success("✅ Session completed successfully!")

# PAGE 5: PROTOCOL LIBRARY
elif page == "📚 Protocol Library":
    st.markdown('<p class="main-header">📚 Protocol Library</p>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["View Protocols", "Add New Protocol"])
    
    with tab1:
        st.markdown('<p class="section-header">Existing Protocols</p>', unsafe_allow_html=True)
        protocols_df = get_protocols()
        if not protocols_df.empty:
            st.dataframe(protocols_df, use_container_width=True)
            # Add protocol deletion feature
            protocol_names = protocols_df['protocol_name'].tolist()
            delete_protocol = st.selectbox("Select protocol to delete", protocol_names)
            if st.button("Delete Selected Protocol", type="primary"):
                c = conn.cursor()
                c.execute("DELETE FROM protocol_library WHERE protocol_name = ?", (delete_protocol,))
                conn.commit()
                st.success(f"✅ Protocol '{delete_protocol}' deleted successfully!")
            
        else:
            st.info("ℹ️ No protocols configured yet")
    
    with tab2:
        st.markdown('<p class="section-header">Add New Protocol</p>', unsafe_allow_html=True)
        
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
                try:
                    c = conn.cursor()
                    c.execute("""INSERT INTO protocol_library 
                               (protocol_name, waveform_type, burst_pulses, inter_pulse_interval,
                                pulse_rate, pulses_per_train, num_trains, inter_train_interval,
                                session_duration)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                             (protocol_name, waveform_type, burst_pulses, inter_pulse_interval,
                              pulse_rate, pulses_per_train, num_trains, inter_train_interval,
                              session_duration))
                    conn.commit()
                    st.success("✅ Protocol added successfully!")
                except sqlite3.IntegrityError:
                    st.error("❌ Protocol with this name already exists")

# PAGE 6: HOLIDAY CALENDAR
elif page == "🎯 Holiday Calendar":
    st.markdown('<p class="main-header">🎯 Holiday Calendar</p>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["View Holidays", "Add Holiday"])
    
    with tab1:
        st.markdown('<p class="section-header">Configured Holidays</p>', unsafe_allow_html=True)
        holidays_df = pd.read_sql_query("SELECT * FROM holidays ORDER BY holiday_date", conn)
        if not holidays_df.empty:
            st.dataframe(holidays_df, use_container_width=True)
        else:
            st.info("ℹ️ No holidays configured")
    
    with tab2:
        st.markdown('<p class="section-header">Add New Holiday</p>', unsafe_allow_html=True)
        
        holiday_date = st.date_input("Holiday Date")
        holiday_name = st.text_input("Holiday Name")
        skip_enabled = st.checkbox("Enable Auto-skip", value=True)
        
        if st.button("Add Holiday", type="primary"):
            if not holiday_name:
                st.error("❌ Holiday name is required")
            else:
                try:
                    c = conn.cursor()
                    c.execute("""INSERT INTO holidays (holiday_date, holiday_name, skip_enabled)
                               VALUES (?, ?, ?)""",
                             (holiday_date, holiday_name, 1 if skip_enabled else 0))
                    conn.commit()
                    st.success("✅ Holiday added successfully!")
                except sqlite3.IntegrityError:
                    st.error("❌ Holiday for this date already exists")

# Footer
st.sidebar.markdown("---")
st.sidebar.info("💡 TMS Integration Dashboard v1.0\nDeveloped by Dr. Aromal S")

