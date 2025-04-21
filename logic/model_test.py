import os
import torch
import torch.nn as nn
import numpy as np
from typing import Optional, List, Dict, Any

from logic.RuleBasedModel import store_model_result

# ================================================
# === Configuration ===
# ================================================
# --- Model Architecture Parameters (MUST MATCH TRAINING) ---
SEQ_LEN = 100        # Sequence length the model expects
NUM_LANDMARKS = 478  # Number of landmarks per frame
NUM_COORDS = 3       # Number of coordinates per landmark (x, y, z)
INPUT_DIM = NUM_LANDMARKS * NUM_COORDS # 478 * 3 = 1434
HIDDEN_DIM = 256     # GRU hidden dimension used during training
NUM_GRU_LAYERS = 2   # Number of GRU layers used during training
DROPOUT_RATE = 0.4   # Dropout rate used during training (doesn't affect eval)
BIDIRECTIONAL_GRU = True # Whether bidirectional GRU was used
OUTPUT_DIM = 1       # Single score output for regression
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

# --- Model Loading ---
# Path relative to model_test.py (based on screenshot: model_test.py is one level down from Models)
MODEL_WEIGHTS_PATH = "./logic/Models/v1.pth"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# --------------------

print(f"--- Model Test Configuration ---")
print(f"Device: {DEVICE}")
print(f"Expected Sequence Length: {SEQ_LEN}")
print(f"Model Path: {MODEL_WEIGHTS_PATH}")
print(f"-----------------------------")

# ================================================
# === Model Definition ===
# ================================================
# (Copied from training script - must match the saved model structure)

class EngagementRegressionModel(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim=1, num_layers=2, dropout=0.5, bidirectional=True):
        super().__init__()
        self.input_dim = input_dim; self.hidden_dim = hidden_dim; self.num_layers = num_layers
        self.bidirectional = bidirectional; self.num_classes = output_dim
        self.frame_norm = nn.LayerNorm(input_dim); gru_input_dim = input_dim
        self.gru = nn.GRU(gru_input_dim, hidden_dim, num_layers=num_layers, batch_first=True,
                          dropout=dropout if num_layers > 1 else 0, bidirectional=bidirectional)
        gru_output_dim = hidden_dim * 2 if bidirectional else hidden_dim
        self.dropout = nn.Dropout(dropout); self.fc1 = nn.Linear(gru_output_dim, hidden_dim // 2)
        self.relu = nn.ReLU(); self.fc2 = nn.Linear(hidden_dim // 2, output_dim)
        self.output_activation = nn.Sigmoid() # Assuming [0,1] output model

    def forward(self, x):
        batch_size, seq_len, num_features = x.shape # Input expected as [batch, seq, features] now
        # The old model expected [b, s, l, c] and reshaped inside
        # If input here is already [b, s, features], remove reshape
        # x = x.reshape(batch_size, seq_len, -1) # Flatten landmarks internally if needed
        if x.shape[2] != self.input_dim: raise ValueError(f"Input dim mismatch")
        x = self.frame_norm(x); gru_out, hn = self.gru(x)
        if self.bidirectional: last_hidden = torch.cat((hn[-2,:,:], hn[-1,:,:]), dim=1)
        else: last_hidden = hn[-1,:,:]
        out = self.dropout(last_hidden); out = self.fc1(out); out = self.relu(out); out = self.fc2(out)
        out = self.output_activation(out); return out
# ================================================

# ================================================
# === Model Loading ===
# ================================================
def load_engagement_model(weights_path: str, device: torch.device) -> Optional[EngagementRegressionModel]:
    """ Loads the pre-trained EngagementRegressionModel. """
    model = None # Initialize return variable
    print(f"\nLoading model weights from: {weights_path}")
    if not os.path.exists(weights_path):
        print(f"Error: Model weights file not found at {weights_path}")
        return model # Return None

    try:
        # Instantiate model with parameters used during training
        model_instance = EngagementRegressionModel(
            input_dim=INPUT_DIM,
            hidden_dim=HIDDEN_DIM,
            output_dim=OUTPUT_DIM,
            num_layers=NUM_GRU_LAYERS,
            dropout=DROPOUT_RATE, # Required for instantiation, ignored in eval mode
            bidirectional=BIDIRECTIONAL_GRU
        )
        # Load the state dictionary
        model_instance.load_state_dict(torch.load(weights_path, map_location=device))
        model_instance.to(device) # Move model to target device
        model_instance.eval() # Set model to evaluation mode
        print("Model loaded successfully and set to evaluation mode.")
        model = model_instance # Assign successful model

    except FileNotFoundError:
         print(f"Error: Weights file not found at {weights_path}")
    except Exception as e:
        print(f"Error loading model state_dict: {e}")

    return model # Return model instance or None

# Load the model globally when the script starts
loaded_model = load_engagement_model(MODEL_WEIGHTS_PATH, DEVICE)
# ================================================


# ================================================
# === Landmark Preprocessing ===
# ================================================

def get_frame_landmarks_from_raw(frame_data: Any) -> Optional[List[Dict]]:
    """ Extracts list of landmark dicts {'x':..,'y':..,'z':..} from frame data. """
    landmarks_list = None
    try:
        # (Extraction logic for Case 1 and Case 2 remains the same)
        if isinstance(frame_data, list) and len(frame_data) > 0:
            if isinstance(frame_data[0], dict): # Case 1
                landmarks_list = frame_data
            elif isinstance(frame_data[0], list): # Case 2
                 inner_list = frame_data[0]
                 if inner_list and isinstance(inner_list[0], dict):
                     landmarks_list = inner_list

        # Validation
        if landmarks_list is not None:
            if len(landmarks_list) == NUM_LANDMARKS: # Check EXACT Count
                 if isinstance(landmarks_list[0], dict) and 'x' in landmarks_list[0]: # Basic Format check
                      pass # Valid - will return landmarks_list below
                 else:
                     landmarks_list = None # Invalid format
            else: # Landmark count mismatch
                 landmarks_list = None # Failed Count check

    except Exception as e:
        landmarks_list = None

    return landmarks_list


def preprocess_landmarks_for_model(
    landmarks_sequence: List[Any],
    seq_len: int = SEQ_LEN,
    num_landmarks: int = NUM_LANDMARKS,
    num_coords: int = NUM_COORDS,
    device: torch.device = DEVICE
    ) -> Optional[torch.Tensor]:
    """ Preprocesses raw landmark sequence into a tensor for the model. """
    processed_tensor = None
    tensor_frames = []
    valid_frames_count = 0

    # 1. Extract and create frame tensors (or placeholders)
    for idx, frame_data in enumerate(landmarks_sequence):
        single_frame_landmarks = get_frame_landmarks_from_raw(frame_data)
        frame_tensor = torch.zeros((num_landmarks, num_coords), dtype=torch.float32) # Default placeholder

        if single_frame_landmarks is not None:
            try:
                frame_array = np.array(
                    [[lm.get('x', 0.0), lm.get('y', 0.0), lm.get('z', 0.0)]
                     for lm in single_frame_landmarks],
                    dtype=np.float32
                )
                frame_tensor = torch.from_numpy(frame_array)
                valid_frames_count += 1
            except Exception as e:
                print(f"Warn: Error converting frame {idx} to tensor: {e}. Using placeholder.")
                frame_tensor = torch.zeros((num_landmarks, num_coords), dtype=torch.float32)

        tensor_frames.append(frame_tensor)

    if valid_frames_count == 0:
        print("Warning: No valid frames found in the input sequence. Proceeding with zero tensor.")

    # 2. Pad or Truncate sequence
    current_len = len(tensor_frames)
    if current_len < seq_len:
        padding_count = seq_len - current_len
        padding = [torch.zeros((num_landmarks, num_coords), dtype=torch.float32) for _ in range(padding_count)]
        tensor_frames.extend(padding)
    elif current_len > seq_len:
        tensor_frames = tensor_frames[-seq_len:]

    # 3. Stack, Flatten, Add Batch Dim, Move to Device
    try:
        sequence_tensor = torch.stack(tensor_frames, dim=0)

        sequence_tensor_flat = sequence_tensor.reshape(seq_len, -1)

        if sequence_tensor_flat.shape[1] != (num_landmarks * num_coords):
             print(f"Error: Unexpected feature dimension after reshape: {sequence_tensor_flat.shape[1]}")
             return None

        processed_tensor = sequence_tensor_flat.unsqueeze(0).to(device)

    except Exception as e:
        print(f"Error during final tensor processing: {e}")
        processed_tensor = None

    return processed_tensor
# ================================================


# ================================================
# === Prediction Function ===
# ================================================
def predict_engagement_dnn(
    extraction_payload: Dict[str, Any],
    model: nn.Module,
    device: torch.device,
    log_data_id: int,
    ) -> Optional[float]:
    """
    Runs inference using the loaded DNN model on data from extraction_payload.

    Args:
        extraction_payload (dict): Dict containing 'landmarks' key with raw landmark data.
        model (nn.Module): The loaded PyTorch model instance.
        device (torch.device): The device to run inference on.

    Returns:
        Optional[float]: The predicted engagement score [0.0, 1.0], or None if prediction fails.
    """
    predicted_score = None # Initialize return variable

    if model is None:
        print("Error: Model is not loaded.")
        return predicted_score
    if not isinstance(extraction_payload, dict):
         print("Error: extraction_payload is not a dictionary.")
         return predicted_score

    landmarks_raw = extraction_payload.get("landmarks")
    if landmarks_raw is None:
        print("Error: 'landmarks' key missing in extraction_payload.")
        return predicted_score
    if not isinstance(landmarks_raw, list):
        print("Error: 'landmarks' data is not a list.")
        return predicted_score


    input_tensor = preprocess_landmarks_for_model(landmarks_raw, device=device)

    if input_tensor is None:
        print("Error: Failed to preprocess landmarks into tensor.")
        return predicted_score # Return None if preprocessing failed

    # 2. Run Inference
    try:
        with torch.no_grad(): # Disable gradient calculations for inference
            output_score_tensor = model(input_tensor) # Model output is [1, 1]

        # Extract scalar score and ensure it's within expected range (due to sigmoid)
        predicted_score = output_score_tensor.item()
        predicted_score = max(0.0, min(1.0, predicted_score)) # Clamp just in case

    except Exception as e:
        print(f"Error during model inference: {e}")
        predicted_score = 0 # Set to None on error

    store_model_result(log_data_id, "v1", predicted_score) # Store the result in the database

    return predicted_score
# ================================================


# ================================================
# === Example Usage ===
# ================================================
if __name__ == "__main__":
    print("\n--- Running Model Test Example ---")

    # ** IMPORTANT: Create realistic dummy data matching your extraction_payload **
    # This dummy data assumes landmarks are already somewhat processed into lists of frames,
    # where each frame is a list of landmark dictionaries.
    # Adjust this based on EXACTLY what your server receives.

    dummy_num_frames = 95 # Simulate a sequence shorter than SEQ_LEN
    dummy_landmarks_per_frame = NUM_LANDMARKS
    dummy_coords = NUM_COORDS

    # Create dummy landmark data (list of frames)
    # Frame format: list of {'x': float, 'y': float, 'z': float} dicts
    dummy_frame_list = []
    for f in range(dummy_num_frames):
        # Simulate some frames might be invalid/missing landmarks occasionally
        if f % 15 == 0:
             frame_landmarks = None # Simulate completely missing frame data
        else:
             # Simulate correct structure but maybe slightly fewer landmarks sometimes (handled by preprocess)
             actual_lm_count = dummy_landmarks_per_frame if f%10 != 0 else dummy_landmarks_per_frame - 5
             frame_landmarks = [{'x': np.random.rand(), 'y': np.random.rand(), 'z': np.random.rand()}
                                for _ in range(actual_lm_count)]
             # Simulate potential nesting [[...]]
             if f % 5 == 0:
                  frame_landmarks = [frame_landmarks]

        dummy_frame_list.append(frame_landmarks)

    # Create the payload dictionary
    dummy_payload = {
        "fps": 10, # Example value
        "interval": 10, # Example value
        "landmarks": dummy_frame_list,
        # Add other keys if your payload has them
    }
    print(f"Created dummy payload with {len(dummy_payload.get('landmarks',[]))} frames.")

    # --- Run Prediction ---
    if loaded_model is not None:
        predicted_score = predict_engagement_dnn(dummy_payload, loaded_model, DEVICE)

        if predicted_score is not None:
            print(f"\nPredicted Engagement Score: {predicted_score:.4f}")
        else:
            print("\nPrediction failed.")
    else:
        print("\nCannot run prediction: Model not loaded.")

    print("\n--- Model Test Example Finished ---")
# ================================================