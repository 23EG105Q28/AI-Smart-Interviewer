import cv2
import numpy as np
import speech_recognition as sr
from textblob import TextBlob
from transformers import pipeline
import threading, time, json, librosa
import random

# Initialize models
sentiment_model = pipeline("sentiment-analysis")
recognizer = sr.Recognizer()

speech_text = ""
analysis_result = {}
is_running = False
scroll_text = ""
scroll_x = 0
scroll_speed = 3  # Default speed
speed_input_active = False
speed_input_text = "3"
program_running = True  # Flag to control program execution

# Sample prompts for reading
SAMPLE_TEXTS = [
    "The quick brown fox jumps over the lazy dog with remarkable agility and grace",
    "Technology has revolutionized the way we communicate and interact with the world around us",
    "Effective communication requires clarity, confidence, and the ability to engage your audience",
    "Success in any field demands dedication, perseverance, and continuous learning",
    "Leadership is not about being in charge, it is about taking care of those in your charge",
    "Innovation distinguishes between a leader and a follower in today's competitive world",
    "The journey of a thousand miles begins with a single step and unwavering determination",
    "Collaboration and teamwork are essential ingredients for achieving extraordinary results"
]

# --- Audio analysis ---
def analyze_audio_tone(audio_data, sample_rate=16000):
    y = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
    if np.max(np.abs(y)) > 0:
        y /= np.max(np.abs(y))
    pitch = librosa.yin(y, fmin=50, fmax=300, sr=sample_rate)
    avg_pitch = np.nanmean(pitch)
    energy_score = min(max((avg_pitch - 100) / 100 * 20, 0), 20)  # 0-20 points
    return energy_score, "Energetic" if avg_pitch > 150 else "Calm"

# --- Text-based soft skill analysis ---
def analyze_text_softskills(text):
    feedback = {}

    # Sentiment as confidence (0-30 points)
    sentiment = sentiment_model(text)[0]
    confidence_score = sentiment["score"] * 30 if sentiment["label"] == "POSITIVE" else sentiment["score"] * 15
    feedback["confidence"] = round(confidence_score, 1)

    # Clarity (grammar)
    blob = TextBlob(text)
    errors = len(blob.correct().words) - len(blob.words)
    clarity_score = max(0, 30 - errors * 5)  # 0-30 points
    feedback["clarity"] = round(clarity_score, 1)

    # Fluency
    avg_sentence_length = sum(len(s.split()) for s in text.split(".")) / max(1, len(text.split(".")))
    filler_words = sum(text.lower().count(w) for w in ["um", "uh", "like", "you know"])
    fluency_score = min(max(avg_sentence_length * 3 - filler_words * 5, 0), 20)  # 0-20 points
    feedback["fluency"] = round(fluency_score, 1)

    # Overall score out of 100
    total_score = feedback["confidence"] + feedback["clarity"] + feedback["fluency"]
    feedback["score"] = round(total_score, 1)

    return feedback

# --- Voice listener thread ---
def listen_speech():
    global speech_text, analysis_result, is_running, program_running
    with sr.Microphone() as source:
        while program_running:
            if not is_running:
                time.sleep(0.5)
                continue
            try:
                print("🎙 Listening...")
                audio = recognizer.listen(source, phrase_time_limit=6)
                if not program_running:  # Check again after listening
                    break
                text = recognizer.recognize_google(audio)
                print("🗣 You said:", text)
                speech_text = text
                analysis_result = analyze_text_softskills(text)
            except Exception as e:
                if is_running and program_running:
                    print("⚠ Speech recognition error:", e)
                continue
    print("🔇 Speech recognition stopped")

# --- Mouse callback for button clicks ---
def mouse_callback(event, x, y, flags, param):
    global is_running, scroll_text, scroll_x, scroll_speed, speed_input_active, speed_input_text
    
    if event == cv2.EVENT_LBUTTONDOWN:
        # Get button coordinates from param
        start_btn, stop_btn, frame_width, speed_field = param
        
        # Check if speed input field clicked
        if (speed_field[0] <= x <= speed_field[2] and 
            speed_field[1] <= y <= speed_field[3]):
            speed_input_active = True
            print("📝 Click on window and type speed value, then press Enter")
        
        # Check if Start button clicked
        elif (start_btn[0] <= x <= start_btn[2] and 
            start_btn[1] <= y <= start_btn[3]):
            if not is_running:
                is_running = True
                scroll_text = random.choice(SAMPLE_TEXTS)
                scroll_x = frame_width  # Start from right edge
                speed_input_active = False  # Deactivate input when starting
                print("▶ Started! Read the scrolling text...")
        
        # Check if Stop button clicked
        elif (stop_btn[0] <= x <= stop_btn[2] and 
              stop_btn[1] <= y <= stop_btn[3]):
            if is_running:
                is_running = False
                scroll_text = ""
                print("⏹ Stopped!")
        else:
            # Click outside - deactivate input
            speed_input_active = False

# --- Webcam display ---
def start_video_display():
    global analysis_result, scroll_text, scroll_x, is_running, scroll_speed, speed_input_active, speed_input_text, program_running
    cap = cv2.VideoCapture(0)
    start_time = time.time()

    # Button properties
    button_height = 50
    button_width = 150
    button_spacing = 20
    
    # Create window and set mouse callback
    window_name = "🧠 AI Soft Skill Evaluator (Enhanced)"
    cv2.namedWindow(window_name)
    
    while cap.isOpened() and program_running:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        
        # Get frame dimensions
        frame_height, frame_width = frame.shape[:2]
        
        # Create extended frame with space for buttons and input field
        extended_height = frame_height + button_height + 80  # Extra space for input field
        extended_frame = np.ones((extended_height, frame_width, 3), dtype=np.uint8) * 50

        # Copy original frame to top portion
        extended_frame[0:frame_height, 0:frame_width] = frame

        # Draw scrolling text if running
        if is_running and scroll_text:
            # Create semi-transparent overlay for text background
            overlay = extended_frame.copy()
            cv2.rectangle(overlay, (0, frame_height - 100), (frame_width, frame_height - 20), 
                         (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, extended_frame, 0.3, 0, extended_frame)
            
            # Draw scrolling text
            font_scale = 1.2
            thickness = 2
            text_size = cv2.getTextSize(scroll_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
            
            # Update scroll position
            scroll_x -= scroll_speed
            
            # Reset when text completely scrolls off left side
            if scroll_x < -text_size[0]:
                scroll_x = frame_width
            
            text_y = frame_height - 50
            cv2.putText(extended_frame, scroll_text, (int(scroll_x), text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), thickness)

        # Display analysis results on video
        y = 40
        for key, val in analysis_result.items():
            text = f"{key.capitalize()}: {val}"
            color = (0, 255, 0) if val > 15 else (0, 255, 255) if val > 10 else (0, 0, 255)
            cv2.putText(extended_frame, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            y += 30

        elapsed = int(time.time() - start_time)
        cv2.putText(extended_frame, f"⏱ Time: {elapsed}s", (20, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

        # Draw Speed Input Field (above buttons)
        speed_label_x = 20
        speed_label_y = frame_height + 20
        cv2.putText(extended_frame, "Scroll Speed:", (speed_label_x, speed_label_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Speed input box
        input_box_x1 = speed_label_x + 150
        input_box_y1 = speed_label_y - 25
        input_box_x2 = input_box_x1 + 80
        input_box_y2 = input_box_y1 + 35
        
        # Draw input box with border
        input_bg_color = (255, 255, 200) if speed_input_active else (255, 255, 255)
        border_color = (0, 255, 255) if speed_input_active else (150, 150, 150)
        cv2.rectangle(extended_frame, (input_box_x1, input_box_y1), 
                     (input_box_x2, input_box_y2), input_bg_color, -1)
        cv2.rectangle(extended_frame, (input_box_x1, input_box_y1), 
                     (input_box_x2, input_box_y2), border_color, 2)
        
        # Display speed value
        display_text = speed_input_text if speed_input_active else str(scroll_speed)
        cv2.putText(extended_frame, display_text, (input_box_x1 + 10, input_box_y1 + 24),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # Add hint text if active
        if speed_input_active:
            cv2.putText(extended_frame, "Type speed (1-20) and press Enter", 
                       (input_box_x2 + 20, speed_label_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Calculate button positions (centered)
        total_buttons_width = (button_width * 2) + button_spacing
        start_x = (frame_width - total_buttons_width) // 2
        button_y = frame_height + 60  # Moved down to make space for input field

        # Draw Start button
        start_button_x1 = start_x
        start_button_y1 = button_y
        start_button_x2 = start_button_x1 + button_width
        start_button_y2 = start_button_y1 + button_height
        
        # Change color if running
        start_color = (100, 150, 100) if is_running else (0, 255, 0)
        cv2.rectangle(extended_frame, (start_button_x1, start_button_y1), 
                     (start_button_x2, start_button_y2), start_color, -1)
        cv2.rectangle(extended_frame, (start_button_x1, start_button_y1), 
                     (start_button_x2, start_button_y2), (0, 200, 0), 2)
        cv2.putText(extended_frame, "START", 
                   (start_button_x1 + 35, start_button_y1 + 32),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

        # Draw Stop button
        stop_button_x1 = start_button_x2 + button_spacing
        stop_button_y1 = button_y
        stop_button_x2 = stop_button_x1 + button_width
        stop_button_y2 = stop_button_y1 + button_height
        
        # Change color if running
        stop_color = (0, 0, 255) if is_running else (100, 100, 150)
        cv2.rectangle(extended_frame, (stop_button_x1, stop_button_y1), 
                     (stop_button_x2, stop_button_y2), stop_color, -1)
        cv2.rectangle(extended_frame, (stop_button_x1, stop_button_y1), 
                     (stop_button_x2, stop_button_y2), (0, 0, 200), 2)
        cv2.putText(extended_frame, "STOP", 
                   (stop_button_x1 + 40, stop_button_y1 + 32),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Set mouse callback with button coordinates
        start_btn_coords = (start_button_x1, start_button_y1, start_button_x2, start_button_y2)
        stop_btn_coords = (stop_button_x1, stop_button_y1, stop_button_x2, stop_button_y2)
        speed_field_coords = (input_box_x1, input_box_y1, input_box_x2, input_box_y2)
        cv2.setMouseCallback(window_name, mouse_callback, 
                            (start_btn_coords, stop_btn_coords, frame_width, speed_field_coords))

        # Handle keyboard input for speed
        key = cv2.waitKey(1) & 0xFF
        
        if speed_input_active:
            if key == 13:  # Enter key
                try:
                    new_speed = int(speed_input_text)
                    if 1 <= new_speed <= 20:
                        scroll_speed = new_speed
                        print(f"✅ Speed set to {scroll_speed}")
                    else:
                        print("⚠ Speed must be between 1 and 20")
                        speed_input_text = str(scroll_speed)
                except ValueError:
                    print("⚠ Invalid speed value")
                    speed_input_text = str(scroll_speed)
                speed_input_active = False
            elif key == 8 or key == 127:  # Backspace
                speed_input_text = speed_input_text[:-1] if len(speed_input_text) > 0 else ""
            elif 48 <= key <= 57:  # Numbers 0-9
                if len(speed_input_text) < 2:  # Limit to 2 digits
                    speed_input_text += chr(key)
        
        if key == ord("q"):
            break
        
        # Check if window was closed
        if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
            print("🚪 Window closed - stopping program...")
            program_running = False
            break

        cv2.imshow(window_name, extended_frame)

    cap.release()
    cv2.destroyAllWindows()
    program_running = False  # Ensure program stops
    
    print("💾 Saving report...")

    # Save detailed report
    final_report = {
        "speech_text": speech_text,
        "analysis": analysis_result,
        "duration": elapsed
    }
    with open("softskill_report.json", "w") as f:
        json.dump(final_report, f, indent=2)
    print("\n✅ Report saved as 'softskill_report.json'")
    print("👋 Program terminated")

# --- Run threads ---
threading.Thread(target=listen_speech, daemon=True).start()
start_video_display()