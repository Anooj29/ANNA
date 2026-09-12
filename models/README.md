# models/

Place the two TFLite model files here before running the robot:

- `person_detect.tflite` - an object-detection model whose class 0 is "person"
  (e.g. an SSD MobileNet variant trained/exported for the TFLite Task API).
- `emotion_model.tflite` - a facial-emotion-classification model with 7
  outputs in this exact order: Angry, Disgust, Fear, Happy, Neutral, Sad,
  Surprise, taking a single-channel (grayscale) face crop as input.

Both paths are configurable via `ROBOT_PERSON_MODEL` / `ROBOT_EMOTION_MODEL`
environment variables if you'd rather store them elsewhere.
