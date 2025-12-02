import streamlit as st
import cv2
import json
import time
import tempfile
import pymongo
import bcrypt
from ultralytics import YOLO
from streamlit_drawable_canvas import st_canvas
from PIL import Image

# ---------------- Streamlit Config (must be first) ----------------
st.set_page_config(page_title="Crowd Monitoring Dashboard", layout="wide")

# ---------------- MongoDB Setup ----------------
MONGO_URI = "mongodb://localhost:27017"   # change if using Atlas
client = pymongo.MongoClient(MONGO_URI)
db = client["crowd_app"]
users_collection = db["users"]

# ---------------- Helper Functions ----------------
def register_user(username, password):
    if users_collection.find_one({"username": username}):
        return False, "Username already exists!"
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users_collection.insert_one({"username": username, "password": hashed_pw})
    return True, "Registration successful!"

def login_user(username, password):
    user = users_collection.find_one({"username": username})
    if not user:
        return False, "User not found!"
    if bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return True, "Login successful!"
    else:
        return False, "Invalid password!"

# ---------------- YOLO Model ----------------
@st.cache_resource
def load_model():
    return YOLO("yolov8s.pt")

model = load_model()

# ---------------- Session State ----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user" not in st.session_state:
    st.session_state.user = None

# ---------------- Authentication UI ----------------
st.title(" Crowd Monitoring Dashboard ")

menu = st.sidebar.selectbox("Menu", ["Login", "Register"])

if not st.session_state.authenticated:
    if menu == "Register":
        st.subheader("Register New User")
        reg_username = st.text_input("Username")
        reg_password = st.text_input("Password", type="password")
        if st.button("Register"):
            success, msg = register_user(reg_username, reg_password)
            if success:
                st.success(msg)
            else:
                st.error(msg)

    elif menu == "Login":
        st.subheader("Login")
        log_username = st.text_input("Username")
        log_password = st.text_input("Password", type="password")
        if st.button("Login"):
            success, msg = login_user(log_username, log_password)
            if success:
                st.success(msg)
                st.session_state.authenticated = True
                st.session_state.user = log_username
                st.rerun()
            else:
                st.error(msg)

# ---------------- Dashboard (only if logged in) ----------------
if st.session_state.authenticated:
    st.success(f"Welcome, {st.session_state['user']}! 🎉 You are logged in.")

    # Sidebar instructions + logout
    st.sidebar.title("📖 How to Use")
    st.sidebar.markdown("""
    1. Upload a video file (mp4, avi, mov).
    2. Draw zones directly on the first frame.
    3. Name each zone in the text fields.
    4. Confirm zones to save them.
    5. Click Start Detection to run YOLO.
    6. Watch live counts update in the dashboard.
    """)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.success("You have been logged out.")
        st.rerun()

    uploaded_file = st.file_uploader("Upload a video file", type=["mp4", "avi", "mov"])
    if uploaded_file is not None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tmp.write(uploaded_file.read())
        tmp.close()
        video_path = tmp.name

        # Show first frame for zone drawing
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            st.error("Could not read video")
        else:
            frame = cv2.resize(frame, (640, 360))
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)

            st.subheader("Draw Zones on Video Frame")
            canvas_result = st_canvas(
                fill_color="rgba(255, 0, 0, 0.3)",
                stroke_width=2,
                stroke_color="blue",
                background_image=pil_img,
                update_streamlit=True,
                height=360,
                width=640,
                drawing_mode="rect",
                key="canvas",
            )

            zones = []
            zone_names = []
            if canvas_result.json_data is not None:
                for i, obj in enumerate(canvas_result.json_data["objects"]):
                    if obj["type"] == "rect":
                        left = int(obj["left"])
                        top = int(obj["top"])
                        width = int(obj["width"])
                        height = int(obj["height"])
                        zones.append((left, top, left + width, top + height))
                        zone_name = st.text_input(f"Enter name for Zone {i+1}", f"Zone {i+1}")
                        zone_names.append(zone_name)

            if zones:
                st.write("📍 Zones:", {zone_names[i]: zones[i] for i in range(len(zones))})
                zones_data = [{"name": zone_names[i], "coords": zones[i]} for i in range(len(zones))]
                with open("zones.json", "w") as f:
                    json.dump(zones_data, f, indent=4)

                run_detection = st.button("▶ Start Detection")
                if run_detection:
                    cap2 = cv2.VideoCapture(video_path)
                    zone_placeholder = st.empty()
                    frame_placeholder = st.empty()
                    chart_placeholder = st.empty()

                    while cap2.isOpened():
                        ret, frame = cap2.read()
                        if not ret:
                            break
                        frame = cv2.resize(frame, (640, 360))
                        results = model(frame, stream=True)
                        zone_count = [0] * len(zones)

                        for result in results:
                            for box in result.boxes:
                                cls_id = int(box.cls[0])
                                if model.names[cls_id] == "person":
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                    cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
                                    for i, (zx1, zy1, zx2, zy2) in enumerate(zones):
                                        if zx1 < cx < zx2 and zy1 < cy < zy2:
                                            zone_count[i] += 1

                        # Update dashboard
                        zone_placeholder.write({zone_names[i]: zone_count[i] for i in range(len(zones))})
                        frame_placeholder.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                        chart_placeholder.bar_chart(zone_count)

                        time.sleep(0.05)

                    cap2.release()