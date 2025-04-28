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
        # Input expected as [batch, seq, features = num_landmarks * num_coords]
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
    model = None
    print(f"\nLoading model weights from: {weights_path}")
    if not os.path.exists(weights_path):
        print(f"Error: Model weights file not found at {weights_path}")
    else:
        try:
            model_instance = EngagementRegressionModel(
                input_dim=INPUT_DIM, hidden_dim=HIDDEN_DIM, output_dim=OUTPUT_DIM,
                num_layers=NUM_GRU_LAYERS, dropout=DROPOUT_RATE, bidirectional=BIDIRECTIONAL_GRU
            )
            model_instance.load_state_dict(torch.load(weights_path, map_location=device))
            model_instance.to(device)
            model_instance.eval()
            print("Model loaded successfully and set to evaluation mode.")
            model = model_instance
        except Exception as e:
            print(f"Error loading model state_dict: {e}")
    return model

loaded_model = load_engagement_model(MODEL_WEIGHTS_PATH, DEVICE)
# ================================================


# ================================================
# === Landmark Preprocessing (Pipeline Style) ===
# ================================================
def preprocess_landmarks_pipeline_style(
    landmarks_sequence: List[Any], # Expects List[List[Dict]] or List[None or -1]
    target_frames: int = SEQ_LEN,
    num_landmarks: int = NUM_LANDMARKS,
    dims: int = NUM_COORDS
    ) -> Optional[torch.Tensor]:
    """
    Preprocesses raw landmark sequence into a tensor stack, mirroring pipeline logic.
    Handles missing frames/landmarks, padding/truncation with -1.0.
    Output shape: (target_frames, num_landmarks, dims)
    """
    if not isinstance(landmarks_sequence, list):
        print("Error: Input landmarks_sequence must be a list.")
        return None

    processed_frames = []
    # Frame-by-Frame Processing
    landmarks = landmarks_sequence[0]
    for frame_data in landmarks:
        # Check for missing frame indicator (None or -1)
        if frame_data is None or frame_data == -1:
            frame_tensor = torch.full((num_landmarks, dims), -1.0, dtype=torch.float32)
        elif isinstance(frame_data, list):
            coords = []
            try:
                for landmark in frame_data:
                    if isinstance(landmark, dict) and 'x' in landmark and 'y' in landmark and 'z' in landmark:
                        coords.append([landmark['x'], landmark['y'], landmark['z']])
                    # else: Skip malformed landmark data silently for brevity

                if not coords: # Treat frame with no valid landmarks as missing
                    frame_tensor = torch.full((num_landmarks, dims), -1.0, dtype=torch.float32)
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

                    frame_tensor = torch.tensor(coords_np, dtype=torch.float32)

            except Exception as e: # Error during coord extraction
                 print(f"Error processing landmarks in a frame: {e}. Treating as missing.")
                 frame_tensor = torch.full((num_landmarks, dims), -1.0, dtype=torch.float32)
        else: # Handle unexpected data type for a frame
            print(f"Warning: Unexpected data type in landmarks_sequence: {type(frame_data)}. Treating as missing frame.")
            frame_tensor = torch.full((num_landmarks, dims), -1.0, dtype=torch.float32)

        processed_frames.append(frame_tensor)

    # Sequence Padding/Truncation
    original_frames = len(processed_frames)
    final_processed_frames = [] # Use a new list for clarity with single return

    if original_frames == 0:
        print("Warning: No frames processed. Returning None.")
        return None # Return None for empty/invalid sequences
    elif original_frames < target_frames:
        pad_frame = torch.full((num_landmarks, dims), -1.0, dtype=torch.float32)
        num_padding_frames = target_frames - original_frames
        final_processed_frames = processed_frames + [pad_frame] * num_padding_frames
    elif original_frames > target_frames:
        final_processed_frames = processed_frames[:target_frames] # Take the *first* target_frames
    else:
        final_processed_frames = processed_frames # No padding/truncation needed

    # Final Tensor Stacking
    tensor_stack = None
    try:
        tensor_stack = torch.stack(final_processed_frames)
    except Exception as e:
        print(f"Error during final tensor stacking: {e}")
        # tensor_stack remains None

    return tensor_stack # Shape: (target_frames, num_landmarks, dims) or None
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
    Uses pipeline-style preprocessing.
    """
    predicted_score = None # Initialize return variable

    if model is None:
        print("Error: Model is not loaded.")
        return predicted_score # Early return on critical error
    if not isinstance(extraction_payload, dict):
         print("Error: extraction_payload is not a dictionary.")
         return predicted_score # Early return on critical error

    landmarks_raw = extraction_payload.get("landmarks")
    if landmarks_raw is None or not isinstance(landmarks_raw, list):
        print("Error: 'landmarks' key missing or data is not a list in payload.")
        return predicted_score # Early return on critical error

    # 1. Preprocess using the pipeline-style function
    # Output shape: (SEQ_LEN, NUM_LANDMARKS, NUM_COORDS)
    sequence_tensor_unbatched = preprocess_landmarks_pipeline_style(
        landmarks_raw,
        target_frames=SEQ_LEN,
        num_landmarks=NUM_LANDMARKS,
        dims=NUM_COORDS
    )

    if sequence_tensor_unbatched is None:
        print("Error: Failed to preprocess landmarks into tensor.")
        # store_model_result(log_data_id, "v1", predicted_score) # Store None if preprocessing fails
        return predicted_score # Return None

    # 2. Reshape, Add Batch Dimension, and Move to Device for Model Input
    # Expected input shape: (1, SEQ_LEN, NUM_LANDMARKS * NUM_COORDS)
    input_tensor = None
    try:
        # Reshape: (SEQ_LEN, NUM_LANDMARKS, NUM_COORDS) -> (SEQ_LEN, NUM_LANDMARKS * NUM_COORDS)
        sequence_tensor_flat = sequence_tensor_unbatched.reshape(SEQ_LEN, -1) # -1 infers INPUT_DIM

        if sequence_tensor_flat.shape[1] != INPUT_DIM:
             print(f"Error: Unexpected feature dimension after reshape: {sequence_tensor_flat.shape[1]}, expected {INPUT_DIM}")
             # predicted_score remains None
        else:
            # Add batch dim: (SEQ_LEN, INPUT_DIM) -> (1, SEQ_LEN, INPUT_DIM)
            input_tensor = sequence_tensor_flat.unsqueeze(0).to(device)

    except Exception as e:
        print(f"Error during tensor reshape/batching: {e}")
        # predicted_score remains None

    # 3. Run Inference (only if input_tensor was created successfully)
    if input_tensor is not None:
        try:
            with torch.no_grad():
                output_score_tensor = model(input_tensor) # Model output is [1, 1]

            predicted_score = output_score_tensor.item()
            predicted_score = max(0.0, min(1.0, predicted_score)) # Clamp [0, 1]

        except Exception as e:
            print(f"Error during model inference: {e}")
            predicted_score = None # Reset score to None on inference error

    store_model_result(log_data_id, "v1", predicted_score) # Store the result (could be None)

    return predicted_score
# ================================================