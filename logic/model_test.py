import os
import time
import onnxruntime
import numpy as np
import json  # For loading extraction_payload if it's a string
from typing import Optional, List, Dict, Any, Tuple

from logic.RuleBasedModel import store_model_result  # Assuming this is correctly importable

# ================================================
# === Configuration ===
# ================================================
SEQ_LEN = 100
NUM_LANDMARKS = 478
NUM_COORDS = 3

IDX_TO_SCORE_MAP_V4: Dict[int, float] = {4: 0.05, 0: 0.30, 1: 0.50, 2: 0.70, 3: 0.95}

IDX_TO_NAME_MAP_V4: Dict[int, str] = {0: 'Not Engaged',1: 'Barely Engaged',2: 'Engaged',3: 'Highly Engaged',4: 'SNP'}

IDX_TO_SCORE_MAP_V1: Dict[int, float] = {4: 0.0, 0: 0.25, 1: 0.5, 2: 0.75, 3: 1.0}  # Original V1 map
IDX_TO_NAME_MAP_V1: Dict[int, str] = {0: 'Not Engaged', 1: 'Barely Engaged', 2: 'Engaged', 3: 'Highly Engaged', 4: 'SNP'}

# --- ONNX Model Paths ---
ONNX_MODEL_V1_PATH = "./logic/Models/v1.onnx"
ONNX_MODEL_V4_PATH = "./logic/Models/v4.onnx"  # Path for the new v4 model

# --- Landmark indices for V4 Distance Normalization (from experiment_config_v4.py) ---
NOSE_TIP_IDX_V4 = 1
LEFT_EYE_OUTER_IDX_V4 = 33
RIGHT_EYE_OUTER_IDX_V4 = 263

print(f"--- ONNX Model Inference Configuration ---")
print(f"Expected Sequence Length: {SEQ_LEN}")
print(f"ONNX Model V1 Path: {ONNX_MODEL_V1_PATH}")
print(f"ONNX Model V4 Path: {ONNX_MODEL_V4_PATH}")
print(f"-----------------------------")


def map_score_to_class_details(score: Optional[float], version: str = "v4") -> Dict[str, Any]:
    """
    Maps a continuous regression score [0, 1] to a discrete class index and name.
    Uses V4 mappings by default.
    """
    details = {"index": -1, "name": "Prediction Failed", "score": score}
    if score is None:
        return details

    idx_to_name_map = IDX_TO_NAME_MAP_V4
    class_index = -1
    if not (0.0 <= score <= 1.0):  # Score should be clamped before this function
        details["name"] = "Invalid Score Range"
    elif 0.0 <= score < 0.175:
        class_index = 4  # SNP
    elif 0.175 <= score < 0.40:
        class_index = 0  # Not Engaged
    elif 0.40 <= score < 0.60:
        class_index = 1  # Barely Engaged
    elif 0.60 <= score < 0.825:
        class_index = 2  # Engaged
    elif 0.825 <= score <= 1.0:
        class_index = 3  # Highly Engaged
    else:  # Should not be reached if score is clamped
        class_index = -1
        details["name"] = "Score Mapping Error"

    if class_index != -1:
        details["index"] = class_index
        details["name"] = idx_to_name_map.get(class_index, "Unknown Index")
    return details


def map_score_to_class_details_v1(score: Optional[float]) -> Dict[str, Any]:
    """
    Maps a continuous regression score [0, 1] to a discrete class index and name for V1.
    """
    details = {"index": -1, "name": "Prediction Failed", "score": score}
    if score is None:
        return details

    class_index = -1
    if not (0.0 <= score <= 1.0):
        details["name"] = "Invalid Score Range"
    elif 0.0 <= score < 0.125:
        class_index = 4  # SNP
    elif 0.125 <= score < 0.375:
        class_index = 0  # Not Engaged
    elif 0.375 <= score < 0.625:
        class_index = 1  # Barely Engaged
    elif 0.625 <= score < 0.875:
        class_index = 2  # Engaged
    elif 0.875 <= score <= 1.0:
        class_index = 3  # Highly Engaged
    else:
        class_index = -1

    if class_index != -1:
        details["index"] = class_index
        details["name"] = IDX_TO_NAME_MAP_V1.get(class_index, "Unknown Index")
    return details


def map_classification_logits_to_class_details(logits: Optional[np.ndarray]) -> Dict[str, Any]:
    """
    Processes classification logits (e.g., applies softmax, gets argmax) and maps to class name.
    """
    details = {"index": -1, "name": "Classification Failed", "raw_logits": None}
    if logits is None or not isinstance(logits, np.ndarray):
        return details

    details["raw_logits"] = logits.tolist()  # Store raw logits

    # Apply softmax to get probabilities
    exp_logits = np.exp(logits - np.max(logits))  # Subtract max for numerical stability
    probabilities = exp_logits / np.sum(exp_logits)

    class_index = int(np.argmax(probabilities))
    class_name = IDX_TO_NAME_MAP_V4.get(class_index, "Unknown Index")  # Use V4 map for classification head

    details["index"] = class_index
    details["name"] = class_name
    details["probabilities"] = probabilities.tolist()
    return details


# ================================================
# === ONNX Model Loading ===
# ================================================
def load_onnx_sessions() -> Tuple[Optional[onnxruntime.InferenceSession], Optional[onnxruntime.InferenceSession]]:
    """ Loads both ONNX models (v1 and v4) into InferenceSessions. """
    session_v1 = None
    session_v4 = None

    # Load V1
    print(f"\nLoading ONNX model V1 from: {ONNX_MODEL_V1_PATH}")
    if not os.path.exists(ONNX_MODEL_V1_PATH):
        print(f"Error: ONNX model V1 file not found at {ONNX_MODEL_V1_PATH}")
    else:
        try:
            session_v1 = onnxruntime.InferenceSession(ONNX_MODEL_V1_PATH, providers=['CPUExecutionProvider'])
            print(
                f"ONNX model V1 loaded successfully. Input Names: {[inp.name for inp in session_v1.get_inputs()]}, Output Names: {[out.name for out in session_v1.get_outputs()]}")
        except Exception as e:
            print(f"Error loading ONNX model V1: {e}")

    # Load V4
    print(f"\nLoading ONNX model V4 from: {ONNX_MODEL_V4_PATH}")
    if not os.path.exists(ONNX_MODEL_V4_PATH):
        print(f"Error: ONNX model V4 file not found at {ONNX_MODEL_V4_PATH}")
    else:
        try:
            session_v4 = onnxruntime.InferenceSession(ONNX_MODEL_V4_PATH, providers=['CPUExecutionProvider'])
            print(
                f"ONNX model V4 loaded successfully. Input Names: {[inp.name for inp in session_v4.get_inputs()]}, Output Names: {[out.name for out in session_v4.get_outputs()]}")
        except Exception as e:
            print(f"Error loading ONNX model V4: {e}")

    return session_v1, session_v4


# Load sessions globally or pass them to the prediction function
onnx_session_v1, onnx_session_v4 = load_onnx_sessions()


# ================================================

# ================================================
# === Landmark Preprocessing & Normalization ===
# ================================================
def apply_distance_normalization_numpy(
        landmarks_frames: np.ndarray,  # Shape (T, N, C) e.g. (100, 478, 3)
        nose_tip_index: int,
        left_eye_index: int,
        right_eye_index: int
) -> np.ndarray:
    """
    Applies distance normalization to landmark frames using NumPy.
    Based on DistanceNormalizationStage.
    """
    normalized_frames_list = []
    for frame_idx in range(landmarks_frames.shape[0]):
        frame_landmarks = landmarks_frames[frame_idx, :, :]  # Shape (N, C)

        # Check for padding frames (all -1.0)
        if np.all(frame_landmarks == -1.0):
            normalized_frames_list.append(frame_landmarks)
            continue

        try:
            center_landmark_coords = frame_landmarks[nose_tip_index, :]  # (C,)
            p1_coords = frame_landmarks[left_eye_index, :]  # (C,)
            p2_coords = frame_landmarks[right_eye_index, :]  # (C,)

            # Check if reference landmarks are valid (not part of padding)
            # Assuming -1.0 is a padding indicator. If any ref coord is -1, skip normalization for this frame.
            if np.any(center_landmark_coords == -1.0) or \
                    np.any(p1_coords == -1.0) or \
                    np.any(p2_coords == -1.0):
                normalized_frames_list.append(frame_landmarks)  # Append original if ref landmarks are invalid
                continue

        except IndexError:
            # This might happen if num_landmarks in data is less than expected indices
            print(
                f"DistanceNormalization: Landmark index out of bounds for frame {frame_idx}. Skipping normalization for this frame.")
            normalized_frames_list.append(frame_landmarks)
            continue

        translated_landmarks = frame_landmarks - center_landmark_coords  # Broadcasting (N,C) - (C,) -> (N,C)

        # Calculate scale factor using X and Y coordinates of eye landmarks
        scale_distance = np.sqrt(
            (p1_coords[0] - p2_coords[0]) ** 2 + \
            (p1_coords[1] - p2_coords[1]) ** 2
        )

        if scale_distance < 1e-6:  # Avoid division by zero or very small numbers
            scaled_landmarks = translated_landmarks  # Append translated but not scaled
        else:
            scaled_landmarks = translated_landmarks / scale_distance

        normalized_frames_list.append(scaled_landmarks)

    if not normalized_frames_list:
        return landmarks_frames  # Should not happen if input was valid

    return np.stack(normalized_frames_list, axis=0)


def preprocess_landmarks_pipeline_style(
        landmarks_sequence: List[Any],
        target_frames: int = SEQ_LEN,
        num_landmarks_expected: int = NUM_LANDMARKS,  # Renamed for clarity
        dims: int = NUM_COORDS
) -> Optional[np.ndarray]:
    if not isinstance(landmarks_sequence, list):
        print("Error: Input landmarks_sequence must be a list.")
        return None

    processed_frames = []
    actual_frames_data = landmarks_sequence
    # Handle potential extra nesting if landmarks_sequence = [[frame1_data, frame2_data,...]]
    if len(landmarks_sequence) == 1 and isinstance(landmarks_sequence[0], list):
        actual_frames_data = landmarks_sequence[0]

    for frame_data in actual_frames_data:
        frame_array = np.full((num_landmarks_expected, dims), -1.0, dtype=np.float32)  # Default to padding
        if frame_data is None or frame_data == -1:
            pass  # Already set to padding
        elif isinstance(frame_data, list):  # List of landmark dicts for a frame
            coords = []
            try:
                for landmark_dict in frame_data:  # landmark_dict is {'x': val, 'y': val, 'z': val}
                    if isinstance(landmark_dict, dict) and \
                            'x' in landmark_dict and 'y' in landmark_dict and 'z' in landmark_dict:
                        coords.append([landmark_dict['x'], landmark_dict['y'], landmark_dict['z']])

                if coords:  # If any valid landmarks were found in the frame
                    coords_np = np.array(coords, dtype=np.float32)
                    current_num_landmarks_in_frame = coords_np.shape[0]

                    if current_num_landmarks_in_frame > num_landmarks_expected:
                        coords_np = coords_np[:num_landmarks_expected, :]
                    elif current_num_landmarks_in_frame < num_landmarks_expected:
                        pad_size = num_landmarks_expected - current_num_landmarks_in_frame
                        padding = np.full((pad_size, dims), -1.0, dtype=np.float32)
                        coords_np = np.vstack([coords_np, padding])
                    frame_array = coords_np
            except Exception as e:
                print(f"Error processing landmarks in a frame: {e}. Treating as missing.")
                # frame_array remains the default padding
        else:
            print(f"Warning: Unexpected data type for a frame: {type(frame_data)}. Treating as missing frame.")
            # frame_array remains the default padding
        processed_frames.append(frame_array)

    # Sequence Padding/Truncation
    original_num_frames = len(processed_frames)
    final_processed_frames_list = []

    if original_num_frames == 0:
        print("Warning: No frames processed from input. Returning None.")
        return None

    if original_num_frames < target_frames:
        pad_frame_template = np.full((num_landmarks_expected, dims), -1.0, dtype=np.float32)
        num_padding_frames = target_frames - original_num_frames
        final_processed_frames_list = processed_frames + [pad_frame_template] * num_padding_frames
    elif original_num_frames > target_frames:
        final_processed_frames_list = processed_frames[:target_frames]
    else:
        final_processed_frames_list = processed_frames

    array_stack = None
    try:
        array_stack = np.stack(final_processed_frames_list)
    except ValueError as e:  # Catches errors from inconsistent shapes if any frame was malformed
        print(f"Error during final array stacking: {e}. Check individual frame processing.")
        # array_stack remains None
    return array_stack


# ================================================

# ================================================
# === Prediction Function (Handles V1 and V4) ===
# ================================================
def predict_engagement_onnx(
        extraction_payload_str: str,  # Assuming extraction_payload is a JSON string
        model_version: str,  # "v1" or "v4"
        log_data_id: int,
        session_v1: Optional[onnxruntime.InferenceSession] = onnx_session_v1,  # Use loaded global sessions
        session_v4: Optional[onnxruntime.InferenceSession] = onnx_session_v4
) -> Optional[Dict[str, Any]]:
    result_dict = None
    model_name_for_storage = f"dnn_{model_version}_onnx"

    # --- Input Validation and Parsing ---
    current_session = None
    if model_version == "v1":
        current_session = session_v1
    elif model_version == "v4":
        current_session = session_v4
    else:
        print(f"Error: Unsupported model version '{model_version}'.")
        # store_model_result(log_data_id, model_name_for_storage, None) # Storing None for score
        return result_dict  # None

    if current_session is None:
        print(f"Error: ONNX session for model {model_version} is not loaded.")
        # store_model_result(log_data_id, model_name_for_storage, None)
        return result_dict  # None

    try:
        # The problem description implies extraction_payload comes from request.get_json(),
        # which means it should already be a dict. If it's a string, it needs parsing.
        # For robustness, let's check and parse if it's a string.
        if isinstance(extraction_payload_str, str):
            extraction_payload = json.loads(extraction_payload_str)
        elif isinstance(extraction_payload_str, dict):
            extraction_payload = extraction_payload_str
        else:
            raise ValueError("extraction_payload must be a dict or a JSON string.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error: Invalid extraction_payload format: {e}")
        # store_model_result(log_data_id, model_name_for_storage, None)
        return result_dict  # None

    landmarks_raw = extraction_payload.get("landmarks")
    if landmarks_raw is None or not isinstance(landmarks_raw, list):
        print("Error: 'landmarks' key missing or data is not a list in payload.")
        # store_model_result(log_data_id, model_name_for_storage, None)
        return result_dict  # None

    # 1. Preprocess landmarks
    sequence_array_unbatched = preprocess_landmarks_pipeline_style(
        landmarks_raw, target_frames=SEQ_LEN, num_landmarks_expected=NUM_LANDMARKS, dims=NUM_COORDS
    )

    if sequence_array_unbatched is None:
        print("Error: Failed to preprocess landmarks into array.")
        # store_model_result(log_data_id, model_name_for_storage, None)
        return result_dict  # None

    # 2. Apply Distance Normalization if V4
    if model_version == "v4":
        print("Applying distance normalization for V4 model...")
        sequence_array_unbatched = apply_distance_normalization_numpy(
            sequence_array_unbatched,
            NOSE_TIP_IDX_V4,
            LEFT_EYE_OUTER_IDX_V4,
            RIGHT_EYE_OUTER_IDX_V4
        )
        print("Distance normalization applied.")

    # 3. Prepare Input for ONNX Model (Add Batch Dimension)
    input_array = None
    try:
        input_array = np.expand_dims(sequence_array_unbatched, axis=0).astype(np.float32)
        expected_shape = (1, SEQ_LEN, NUM_LANDMARKS, NUM_COORDS)
        if input_array.shape != expected_shape:
            print(f"Error: Input array shape mismatch! Got {input_array.shape}, Expected {expected_shape}")
            # store_model_result(log_data_id, model_name_for_storage, None)
            return result_dict  # None
    except Exception as e:
        print(f"Error during input array preparation (batching/typing): {e}")
        # store_model_result(log_data_id, model_name_for_storage, None)
        return result_dict  # None

    # 4. Run Inference
    try:
        input_name = current_session.get_inputs()[0].name
        ort_inputs = {input_name: input_array}

        if model_version == "v1":
            output_name_reg = current_session.get_outputs()[0].name  # V1 has one output
            ort_outs = current_session.run([output_name_reg], ort_inputs)
            raw_regression_score = float(ort_outs[0][0][0])  # (batch, 1)

            # Clamp score
            regression_score = max(0.0, min(1.0, raw_regression_score))

            # Map to class details
            # Use V1 specific mapping if needed, otherwise use the general one
            prediction_details_reg = map_score_to_class_details_v1(regression_score)

            result_dict = {
                "score": regression_score,  # This is the primary regression score
                "name": prediction_details_reg.get("name", "Unknown"),
                "index": prediction_details_reg.get("index", -1)
                # No separate classification head for V1
            }
            # store_model_result(log_data_id, model_name_for_storage, regression_score)

        elif model_version == "v4":
            # V4 has two outputs: "regression_scores", "classification_logits"
            # Order matters based on ONNX export config
            output_names = [out.name for out in current_session.get_outputs()]
            # Assuming order from experiment_config_v4.py: ["regression_scores", "classification_logits"]
            # If unsure, print output_names to verify
            # print(f"V4 Output names from ONNX: {output_names}")

            # Make sure these names match your ONNX model's output names
            # If they are different, adjust here.
            # From experiment_config_v4.py:
            # output_names: ["regression_scores", "classification_logits"],
            onnx_output_names = ["regression_scores", "classification_logits"]

            ort_outs = current_session.run(onnx_output_names, ort_inputs)

            raw_regression_score = float(ort_outs[0][0][0])  # regression_scores (batch, 1)
            classification_logits = ort_outs[1][0]  # classification_logits (batch, num_classes)

            # Process regression output
            regression_score = max(0.0, min(1.0, raw_regression_score))
            prediction_details_reg = map_score_to_class_details(regression_score, version="v4")

            # Process classification output
            prediction_details_cls = map_classification_logits_to_class_details(classification_logits)

            result_dict = {
                "score": regression_score,  # Regression head score
                "name": prediction_details_reg.get("name", "Unknown"),  # Mapped from regression
                "index": prediction_details_reg.get("index", -1),  # Mapped from regression
                "classification_head_name": prediction_details_cls.get("name", "Unknown"),
                "classification_head_index": prediction_details_cls.get("index", -1),
                "classification_head_probabilities": prediction_details_cls.get("probabilities"),
                "raw_regression_score": raw_regression_score,  # Optional: for debugging
                "raw_classification_logits": prediction_details_cls.get("raw_logits")  # Optional: for debugging
            }
            # store_model_result(log_data_id, model_name_for_storage, regression_score) # Store primary score
            # Potentially store classification result too if needed:
            # store_classification_result(log_data_id, model_name_for_storage + "_cls", prediction_details_cls)

    except Exception as e:
        print(f"Error during ONNX inference for model {model_version}: {e}")
        # result_dict remains None
        # store_model_result(log_data_id, model_name_for_storage, None)

    # Store result (even if None, to indicate an attempt was made)
    # The `store_model_result` function in the original code only took the score.
    # If you want to store more details, you'll need to modify it or use a different function.
    # For now, we'll assume it logs the primary regression score.
    primary_score_to_log = None
    if result_dict and "score" in result_dict:
        primary_score_to_log = result_dict["score"]

    # Temporarily commenting out store_model_result as its definition is not provided here
    # and to avoid NameError if it's not globally available in this exact context.
    # You should ensure this function is correctly defined and called in your actual application.
    # if log_data_id is not None: # Ensure log_data_id is valid
    #    store_model_result(log_data_id, model_name_for_storage, primary_score_to_log)

    return result_dict
