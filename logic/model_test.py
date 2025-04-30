import os
import time
import onnxruntime
import numpy as np
from typing import Optional, List, Dict, Any

from logic.RuleBasedModel import store_model_result

# ================================================
# === Configuration ===
# ================================================
# --- Model Input/Output Parameters (MUST MATCH ONNX MODEL EXPORT) ---
# These are less critical for loading the ONNX model itself, but crucial
# for ensuring the preprocessing creates data of the correct shape.
SEQ_LEN = 100        # Sequence length the model expects
NUM_LANDMARKS = 478  # Number of landmarks per frame
NUM_COORDS = 3       # Number of coordinates per landmark (x, y, z)
INPUT_DIM = NUM_LANDMARKS * NUM_COORDS # 478 * 3 = 1434 - Used in preprocessing validation

# --- Mappings (Still needed for interpreting output if required later) ---
LABEL_TO_IDX_MAP = {
    'Not Engaged': 0, 'Barely Engaged': 1, 'Engaged': 2, 'Highly Engaged': 3,
    'not engaged': 0, 'not-engaged': 0, 'Not-Engaged': 0,
    'barely engaged': 1, 'barely-engaged': 1, 'Barely-engaged': 1,
    'highly engaged': 3, 'highly-engaged': 3, 'Highly-Engaged': 3,
    'snp(subject not present)': 4, 'SNP(Subject Not Present)': 4, 'SNP': 4,
}
IDX_TO_SCORE_MAP = {4: 0.0, 0: 0.25, 1: 0.5, 2: 0.75, 3: 1.0}
IDX_TO_NAME_MAP = {0: 'Not Engaged', 1: 'Barely Engaged', 2: 'Engaged', 3: 'Highly Engaged', 4: 'SNP'}
# ---------------------------------------------------------

# --- ONNX Model Loading ---
ONNX_MODEL_PATH = "./logic/Models/v1.onnx" # Path to the ONNX model file
# ONNX Runtime will automatically use available providers.
# You can specify providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
# if you want to prioritize GPU (requires onnxruntime-gpu).
# Default is usually CPU.
# --------------------

print(f"--- ONNX Model Inference Configuration ---")
print(f"Expected Sequence Length: {SEQ_LEN}")
print(f"ONNX Model Path: {ONNX_MODEL_PATH}")
print(f"-----------------------------")


def map_score_to_class_details(score: Optional[float]) -> Dict[str, Any]:
    """
    Maps a continuous regression score [0, 1] to a discrete class index and name.

    Args:
        score (Optional[float]): The predicted regression score.

    Returns:
        Dict[str, Any]: A dictionary containing 'index' (int) and 'name' (str).
                        Returns index -1 and appropriate name for invalid/None scores.
    """
    if score is None:
        return {"index": -1, "name": "Prediction Failed"}
    if not (0.0 <= score <= 1.0):
         return {"index": -1, "name": "Invalid Score Range"}

    # Thresholds centered between target scores (0.0, 0.25, 0.5, 0.75, 1.0)
    if 0.0 <= score < 0.125: class_index = 4 # SNP
    elif 0.125 <= score < 0.375: class_index = 0 # Not Engaged
    elif 0.375 <= score < 0.625: class_index = 1 # Barely Engaged
    elif 0.625 <= score < 0.875: class_index = 2 # Engaged
    elif 0.875 <= score <= 1.0: class_index = 3 # Highly Engaged
    else: class_index = -1 # Fallback, should be caught by initial check

    class_name = IDX_TO_NAME_MAP.get(class_index, "Unknown Index")
    return {"index": class_index, "name": class_name}


# ================================================
# === ONNX Model Loading ===
# ================================================
def load_onnx_session(onnx_model_path: str) -> Optional[onnxruntime.InferenceSession]:
    """ Loads the ONNX model into an InferenceSession. """
    session = None
    print(f"\nLoading ONNX model from: {onnx_model_path}")
    if not os.path.exists(onnx_model_path):
        print(f"Error: ONNX model file not found at {onnx_model_path}")
    else:
        try:
            # Create an inference session for the ONNX model
            # Providers can be specified, e.g., ['CUDAExecutionProvider', 'CPUExecutionProvider']
            # If not specified, ONNX Runtime uses available providers (usually CPU first).
            session = onnxruntime.InferenceSession(onnx_model_path, providers=['CPUExecutionProvider']) # Explicitly use CPU for broader compatibility
            print(f"ONNX model loaded successfully. Input Names: {[inp.name for inp in session.get_inputs()]}, Output Names: {[out.name for out in session.get_outputs()]}")
        except Exception as e:
            print(f"Error loading ONNX model: {e}")
            print("Ensure onnxruntime is installed (`pip install onnxruntime`) and the model file is valid.")
    return session


# Load the ONNX session globally or pass it to the prediction function
onnx_session = load_onnx_session(ONNX_MODEL_PATH)
# ================================================


# ================================================
# === Landmark Preprocessing (Pipeline Style) ===
# ================================================
def preprocess_landmarks_pipeline_style(
    landmarks_sequence: List[Any], # Expects List[List[Dict]] or List[None or -1]
    target_frames: int = SEQ_LEN,
    num_landmarks: int = NUM_LANDMARKS,
    dims: int = NUM_COORDS
    ) -> Optional[np.ndarray]: # Return NumPy array for ONNX
    """
    Preprocesses raw landmark sequence into a NumPy array stack.
    Handles missing frames/landmarks, padding/truncation with -1.0.
    Output shape: (target_frames, num_landmarks, dims)
    """
    if not isinstance(landmarks_sequence, list):
        print("Error: Input landmarks_sequence must be a list.")
        return None

    processed_frames = []
    # Frame-by-Frame Processing
    # Ensure we handle the nested list structure correctly if landmarks_sequence = [[frame1_data, frame2_data,...]]
    actual_frames_data = landmarks_sequence
    if len(landmarks_sequence) == 1 and isinstance(landmarks_sequence[0], list):
         actual_frames_data = landmarks_sequence[0] # Handle potential extra nesting

    for frame_data in actual_frames_data:
        # Check for missing frame indicator (None or -1)
        if frame_data is None or frame_data == -1:
            # Use NumPy array for consistency
            frame_array = np.full((num_landmarks, dims), -1.0, dtype=np.float32)
        elif isinstance(frame_data, list):
            coords = []
            try:
                for landmark in frame_data:
                    if isinstance(landmark, dict) and 'x' in landmark and 'y' in landmark and 'z' in landmark:
                        coords.append([landmark['x'], landmark['y'], landmark['z']])
                    # else: Skip malformed landmark data silently

                if not coords: # Treat frame with no valid landmarks as missing
                    frame_array = np.full((num_landmarks, dims), -1.0, dtype=np.float32)
                else:
                    coords_np = np.array(coords, dtype=np.float32)
                    current_num_landmarks = coords_np.shape[0]

                    # Pad or Truncate landmarks within the frame
                    if current_num_landmarks < num_landmarks:
                        pad_size = num_landmarks - current_num_landmarks
                        padding = np.full((pad_size, dims), -1.0, dtype=np.float32)
                        coords_np = np.vstack([coords_np, padding])
                    elif current_num_landmarks > num_landmarks:
                        coords_np = coords_np[:num_landmarks, :]

                    frame_array = coords_np # Already a NumPy array

            except Exception as e: # Error during coord extraction
                 print(f"Error processing landmarks in a frame: {e}. Treating as missing.")
                 frame_array = np.full((num_landmarks, dims), -1.0, dtype=np.float32)
        else: # Handle unexpected data type for a frame
            print(f"Warning: Unexpected data type in landmarks_sequence: {type(frame_data)}. Treating as missing frame.")
            frame_array = np.full((num_landmarks, dims), -1.0, dtype=np.float32)

        processed_frames.append(frame_array)

    # Sequence Padding/Truncation
    original_frames = len(processed_frames)
    final_processed_frames = []

    if original_frames == 0:
        print("Warning: No frames processed. Returning None.")
        return None # Return None for empty/invalid sequences
    elif original_frames < target_frames:
        pad_frame = np.full((num_landmarks, dims), -1.0, dtype=np.float32)
        num_padding_frames = target_frames - original_frames
        final_processed_frames = processed_frames + [pad_frame] * num_padding_frames
    elif original_frames > target_frames:
        final_processed_frames = processed_frames[:target_frames] # Take the *first* target_frames
    else:
        final_processed_frames = processed_frames # No padding/truncation needed

    # Final Array Stacking
    array_stack = None
    try:
        # Stack the list of NumPy arrays into a single NumPy array
        array_stack = np.stack(final_processed_frames)
    except Exception as e:
        print(f"Error during final array stacking: {e}")
        # array_stack remains None

    return array_stack # Shape: (target_frames, num_landmarks, dims) or None
# ================================================


# ================================================
# === Prediction Function (ONNX Version) ===
# ================================================
def predict_engagement_onnx(
    extraction_payload: Dict[str, Any],
    session: onnxruntime.InferenceSession,
    log_data_id: int,
    ) -> Optional[Dict[str, Any]]: # Return dict with score, index, name
    """
    Runs inference using the loaded ONNX model and returns score and classification details.
    """
    predicted_score = None
    prediction_details = None

    # --- Input Validation ---
    if session is None:
        print("Error: ONNX session is not loaded.")
        store_model_result(log_data_id, "v1_onnx", 0.0)
        return None
    if not isinstance(extraction_payload, dict):
         print("Error: extraction_payload is not a dictionary.")
         store_model_result(log_data_id, "v1_onnx", 0.0)
         return None
    landmarks_raw = extraction_payload.get("landmarks")
    if landmarks_raw is None or not isinstance(landmarks_raw, list):
        print("Error: 'landmarks' key missing or data is not a list in payload.")
        store_model_result(log_data_id, "v1_onnx", 0.0)
        return None

    # 1. Preprocess landmarks
    # Expected output shape: (SEQ_LEN, NUM_LANDMARKS, NUM_COORDS) -> Rank 3
    sequence_array_unbatched = preprocess_landmarks_pipeline_style(
        landmarks_raw, target_frames=SEQ_LEN, num_landmarks=NUM_LANDMARKS, dims=NUM_COORDS
    )

    if sequence_array_unbatched is None:
        print("Error: Failed to preprocess landmarks into array.")
        store_model_result(log_data_id, "v1_onnx", 0.0)
        return None

    # 2. Prepare Input for ONNX Model (Add Batch Dimension)
    # The ONNX model expects a 4D input: (batch_size, seq_len, num_landmarks, num_coords)
    input_array = None
    try:
        # Add batch dimension to the front -> Shape: (1, SEQ_LEN, NUM_LANDMARKS, NUM_COORDS) -> Rank 4
        input_array = np.expand_dims(sequence_array_unbatched, axis=0).astype(np.float32)

        # --- Shape Validation (Crucial Debug Step) ---
        expected_shape = (1, SEQ_LEN, NUM_LANDMARKS, NUM_COORDS)
        if input_array.shape != expected_shape:
            print(f"Error: Input array shape mismatch! Got {input_array.shape}, Expected {expected_shape}")
            store_model_result(log_data_id, "v1_onnx", 0.0)
            return None # Stop before inference if shape is wrong

    except Exception as e:
        print(f"Error during input array preparation (batching/typing): {e}")
        store_model_result(log_data_id, "v1_onnx", 0.0)
        return None

    # 3. Run Inference
    try:
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        ort_inputs = {input_name: input_array} # Use the 4D input_array

        # Run inference
        ort_outs = session.run([output_name], ort_inputs)

        # Extract the score - ort_outs is a list containing the output array(s)
        # Assuming the model output shape is (batch_size, 1) -> (1, 1)
        predicted_score = float(ort_outs[0][0][0]) # Extract scalar float value

        # Clamp score to expected [0, 1] range AFTER inference
        predicted_score = max(0.0, min(1.0, predicted_score))

    except Exception as e:
        print(f"Error during ONNX inference: {e}")
        # predicted_score remains None if inference fails

    # 4. Map score to class details (handles None score internally)
    prediction_details = map_score_to_class_details(predicted_score)
    prediction_details["score"] = predicted_score # Add the score (potentially None)

    # Store the raw score (could be None)
    store_model_result(log_data_id, "v1_onnx", predicted_score)

    # Return the dictionary containing score, index, and name
    return prediction_details
# ================================================
# ================================================
