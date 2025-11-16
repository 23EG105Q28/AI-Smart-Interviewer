"""
Test TTS Audio Output
Run this to verify your speakers are working with pyttsx3
"""
import pyttsx3
import time

print("="*80)
print("TTS AUDIO TEST")
print("="*80)
print("\n🔊 Testing your speakers with pyttsx3...")
print("📢 You should hear THREE test messages.\n")

try:
    # Test 1: Simple message
    print("Test 1: Simple message")
    print("🗣️ Speaking: 'Test number one. Can you hear me?'")
    engine = pyttsx3.init()
    engine.setProperty('rate', 170)
    engine.setProperty('volume', 1.0)
    engine.say("Test number one. Can you hear me?")
    engine.runAndWait()
    time.sleep(0.5)  # Delay after speaking
    del engine  # Clean up
    print("✅ Test 1 complete\n")
    time.sleep(1)
    
    # Test 2: Louder and slower
    print("Test 2: Slower speech")
    print("🗣️ Speaking: 'This is test number two, speaking more slowly'")
    engine2 = pyttsx3.init()
    engine2.setProperty('rate', 150)
    engine2.setProperty('volume', 1.0)
    engine2.say("This is test number two, speaking more slowly")
    engine2.runAndWait()
    time.sleep(0.5)  # Delay after speaking
    del engine2  # Clean up
    print("✅ Test 2 complete\n")
    time.sleep(1)
    
    # Test 3: Interview question
    print("Test 3: Interview-style question")
    print("🗣️ Speaking interview question...")
    engine3 = pyttsx3.init()
    engine3.setProperty('rate', 170)
    engine3.setProperty('volume', 1.0)
    question = "Thank you for joining today. Let's start - can you walk me through your professional background?"
    engine3.say(question)
    engine3.runAndWait()
    time.sleep(0.5)  # Delay after speaking
    del engine3  # Clean up
    print("✅ Test 3 complete\n")
    
    print("="*80)
    print("🎉 ALL TESTS COMPLETE!")
    print("="*80)
    print("\nIf you heard all three messages, your TTS is working correctly.")
    print("If you didn't hear anything:")
    print("  1. Check your speaker/headphone volume")
    print("  2. Check Windows Sound Mixer (make sure Python isn't muted)")
    print("  3. Try different speakers/headphones")
    print("  4. Check your default audio output device in Windows settings")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
