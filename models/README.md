# models/

Place the two TFLite model files here before running the robot:

- `person_detect.tflite` - an SSD-style object-detection model trained on
  COCO. ANNA uses it for **every** object class she reports, not just
  people: class 0 is "person", and chair (56), couch (57), bed (59),
  dining table (60) and tv (62) are read from the same model, so there is
  no extra cost for the furniture classes.
  A good default is `ssd_mobilenet_v1_1_metadata_1.tflite` or
  `efficientdet_lite0.tflite` from the TFLite model zoo.
- `emotion_model.tflite` - a facial-emotion-classification model with 7
  outputs in this exact order: Angry, Disgust, Fear, Happy, Neutral, Sad,
  Surprise, taking a face crop as input.

## Which model files work

The loader inspects each model rather than assuming a fixed layout, so it
accepts more exports than the original code did:

- **Any output order.** Boxes / classes / scores / count are identified by
  tensor shape and name, not by index, because different exports order them
  differently.
- **Float or quantised.** uint8/int8 models have their quantisation scale
  applied on the way in and removed on the way out.
- **Greyscale or colour emotion models.** The input tensor's channel count
  decides which conversion is applied.

## Optional: a custom label map

Set `ROBOT_LABEL_MAP=/path/to/labels.txt` to use your model's own labels
instead of the built-in COCO subset. Both common formats are read: one
label per line (the line number is the class id), or `<id> <label>` per
line. Then set `ROBOT_DETECTION_CLASSES` to the names you want reported.

Both model paths are configurable via `ROBOT_PERSON_MODEL` /
`ROBOT_EMOTION_MODEL` if you'd rather store them elsewhere.
## Optional: offline speech recognition

ANNA can use Vosk for offline microphone speech recognition when
`ROBOT_MIC_ENABLED=true`.

Download the Vosk model:

- `vosk-model-small-en-us-0.15`

Place the extracted model directory here:

`models/vosk-model-small-en-us-0.15/`

The model path can be changed with:

`VOSK_MODEL_PATH=/path/to/vosk-model`

The Vosk model is not committed to this repository because model files can
be large. The repository only documents the expected model and location.