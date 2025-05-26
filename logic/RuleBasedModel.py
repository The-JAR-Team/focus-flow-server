from db.DB import DB
import math

from db.db_api import store_model_result


def flatten_landmarks(landmarks, expected_frames=None):
    """
    If landmarks is a list with a single element that is itself a list of frames,
    then return that inner list.
    If not, return the original landmarks list.
    """
    if (
            isinstance(landmarks, list) and len(landmarks) == 1 and
            isinstance(landmarks[0], list)
    ):
        inner = landmarks[0]
        # If expected_frames is given, check if the inner list length matches.
        if expected_frames is None or len(inner) == expected_frames:
            return inner
    return landmarks


def get_frame_landmarks(frame):
    """
    From a given frame, which might have a nested structure (multiple detection sets),
    extract the landmarks for the face. This function assumes that when nested, the first
    detection is the desired one.
    """
    if not frame or not isinstance(frame, list):
        return []
    # If the first element is a list but the inner dictionary is not detected,
    # assume that frame is a nested list (e.g. a list of detections).
    if isinstance(frame[0], list):
        # Here we assume the first set in the nested list holds 478 landmarks.
        return frame[0]
    return frame


def RuleBasedModel(extraction_payload, log_data_id):
    """
    Rule-based model for attention detection using facial landmarks.
    Processes the raw extraction payload and returns an attention score.

    Args:
        extraction_payload (dict): Contains landmarks, fps, interval, etc.
        log_data_id (int): ID to associate with results (storage disabled for now)

    Returns:
        float: Attention score between 0.0 and 1.0
    """
    try:
        fps = extraction_payload.get("fps", 0)
        interval = extraction_payload.get("interval", 0)
        landmarks = extraction_payload.get("landmarks", [])

        # Determine expected number of frames from fps and interval
        expected_frames = fps * interval if fps and interval else None

        # Flatten landmarks if needed (unpack one extra level)
        landmarks = flatten_landmarks(landmarks, expected_frames)

        print(f"FPS: {fps}, Interval: {interval}, Number of frames: {len(landmarks)}")
        if len(landmarks) > 0:
            # Optionally, show landmark count per frame after extraction
            sample_landmarks = get_frame_landmarks(landmarks[0])
            print(f"Each frame expected to have ~{len(sample_landmarks)} landmarks")

        attention_score = calculate_attention_score(landmarks, fps, interval)

        # Uncomment to store the result to DB:
        store_model_result(log_data_id, "RuleBasedModel", attention_score)

        return attention_score

    except Exception as e:
        print(f"Error in RuleBasedModel: {e}")
        return 0.5  # Default value in case of errors


def calculate_attention_score(landmarks, fps, interval):
    """
    Calculate attention score using a point-based system with weighted frames.
    Frames in the last 2 seconds of the intended 10s interval have higher weight.

    Starting at 1.0, points are deducted for:
      - Missing face detection (0.3 of frame score weight)
      - Not looking at screen (1.0 of frame score weight)
      - Excessive movement (0.5 of frame score weight)

    Args:
        landmarks (list): List of frames (each frame a list of landmarks)
        fps (int): Frames per second (can be variable, used for context)
        interval (int): Intended time interval (in seconds, expected to be 10)

    Returns:
        float: Final attention score between 0.0 and 1.0.
    """
    num_landmarks = len(landmarks)
    if not landmarks or num_landmarks == 0:
        print("No landmarks received, returning default score.")
        return 0.5 # Cannot compute properly

    # --- Weighting Calculation ---
    intended_interval = 10.0  # We assume the target is always 10 seconds
    late_period_duration = 2.0  # The last 2 seconds are more important
    early_period_duration = intended_interval - late_period_duration # First 8 seconds

    # Define the proportion of total weight for each period
    late_weight_proportion = 0.6  # Last 2s account for 60% of the score importance
    early_weight_proportion = 1.0 - late_weight_proportion # First 8s account for 40%

    # Calculate how many *actual* frames fall into late period (proportionally)
    # Use actual interval if significantly different from 10?
    # For now, assume interval is close to 10 and base proportion on that.
    # If interval is very different, this might need adjustment.
    if interval > 0:
        late_frames_ratio = late_period_duration / interval
    else:
        # If interval is 0, fallback to assuming 10s, or handle error
        print("Warning: Interval is 0, assuming 10s for frame ratio calculation.")
        late_frames_ratio = late_period_duration / 10.0 if num_landmarks > 0 else 0

    num_late_frames = round(num_landmarks * late_frames_ratio)
    # Ensure at least one frame is in late period if possible and ratio > 0
    if late_frames_ratio > 0 and num_late_frames == 0 and num_landmarks > 0:
        num_late_frames = 1
    # Ensure late frames don't exceed total frames
    num_late_frames = min(num_late_frames, num_landmarks)

    num_early_frames = num_landmarks - num_late_frames

    # Calculate weight per frame in each period
    weight_per_early_frame = 0.0
    weight_per_late_frame = 0.0
    total_weight_sum = 1.0 # The total potential penalty sum

    if num_early_frames > 0:
        weight_per_early_frame = (total_weight_sum * early_weight_proportion) / num_early_frames
    else:
        # If no early frames, distribute early weight proportion to late frames
        if num_late_frames > 0:
            late_weight_proportion += early_weight_proportion # Give all weight to late frames
            early_weight_proportion = 0.0

    if num_late_frames > 0:
        weight_per_late_frame = (total_weight_sum * late_weight_proportion) / num_late_frames
    else:
         # If somehow no late frames (e.g., very few total frames assigned early), distribute late weight to early
        if num_early_frames > 0:
            early_weight_proportion += late_weight_proportion # Give all weight to early frames
            late_weight_proportion = 0.0
            # Recalculate early weight per frame
            weight_per_early_frame = (total_weight_sum * early_weight_proportion) / num_early_frames


    print(f"Total frames: {num_landmarks}")
    print(f"Frames assigned to early period ({early_period_duration}s): {num_early_frames}, Weight per frame: {weight_per_early_frame:.4f}")
    print(f"Frames assigned to late period ({late_period_duration}s): {num_late_frames}, Weight per frame: {weight_per_late_frame:.4f}")

    # --- Score Calculation Loop ---
    score = 1.0
    prev_frame = None
    start_index_late = num_early_frames # Index where late period begins

    print(f"\nStarting attention calculation with weighted frames...")

    for frame_idx, frame in enumerate(landmarks):
        # Determine the weight for the current frame
        is_late_frame = frame_idx >= start_index_late
        current_frame_weight = weight_per_late_frame if is_late_frame else weight_per_early_frame
        period_name = "LATE" if is_late_frame else "EARLY"

        # Extract the actual set of landmarks from the frame
        landmarks_in_frame = get_frame_landmarks(frame)
        print(f"\nProcessing Frame {frame_idx} ({period_name}) - Weight: {current_frame_weight:.4f}")
        print(f"  Landmarks found: {len(landmarks_in_frame)}")

        # Check for empty data
        if not landmarks_in_frame or len(landmarks_in_frame) < 5:
            deduction = 0.3 * current_frame_weight
            score -= deduction
            print(f"  Insufficient data, deducting {deduction:.4f}")
            prev_frame = None # Reset prev_frame as current is invalid for movement check
            continue

        # Check if a face is detected (simple heuristic)
        face_detected = len(landmarks_in_frame) >= 5 # Reuse existing simple check
        if not face_detected:
            deduction = 0.3 * current_frame_weight
            score -= deduction
            print(f"  Face not detected properly, deducting {deduction:.4f}")
            prev_frame = None # Reset prev_frame
            continue

        # Check orientation and movement
        try:
            is_looking, face_center, check_results = check_looking_at_screen(landmarks_in_frame)
            if not is_looking:
                deduction = 1.0 * current_frame_weight
                score -= deduction
                print(f"  Not looking at screen, deducting {deduction:.4f} - {check_results}")
                # Note: We might still check movement even if not looking

            # Calculate movement if previous frame exists and was valid
            if prev_frame is not None:
                prev_landmarks_in_frame = get_frame_landmarks(prev_frame)
                # Ensure previous frame also had enough landmarks for a valid comparison
                if prev_landmarks_in_frame and len(prev_landmarks_in_frame) >= 5:
                    movement = check_movement(landmarks_in_frame, prev_landmarks_in_frame)
                    print(f"  Movement score = {movement:.4f}")
                    if movement > 0.2: # Keep existing threshold
                        deduction = 0.5 * current_frame_weight
                        score -= deduction
                        print(f"  Excessive movement, deducting {deduction:.4f}")
                else:
                     print("  Skipping movement check: Previous frame invalid.")
            else:
                print("  Skipping movement check: No valid previous frame.")

            # Update prev_frame *only if* the current frame was valid
            prev_frame = frame

        except Exception as e:
            print(f"  Error processing frame {frame_idx}: {e}")
            # Apply a standard penalty for processing errors
            deduction = 0.3 * current_frame_weight
            score -= deduction
            print(f"  Deducting {deduction:.4f} due to error.")
            prev_frame = None # Reset prev_frame after error

    final_score = max(0.0, min(1.0, score))
    print(f"\nFinal attention score: {final_score:.4f}")
    return final_score


def check_looking_at_screen(landmarks):
    """
    Check if a person is looking at the screen based on facial landmarks.
    Assumes landmarks is a flat list of dictionaries with keys 'x', 'y', and 'z'.

    Returns:
        tuple: (is_looking (bool), face_center (tuple), check_results (dict))
    """
    check_results = {
        "z_diff_too_high": False,
        "y_pos_too_high": False,
        "y_pos_too_low": False,
        "too_far_side": False,
        "eyes_not_level": False
    }

    # Define key landmark indices based on MediaPipe's 478 landmark model.
    # You might need to adjust these indices to match your version.
    NOSE_TIP = 4
    LEFT_EYE = 33
    RIGHT_EYE = 263
    CHIN = 152
    FOREHEAD = 10

    # For eye level consistency, use two indices per eye (if available)
    LEFT_EYE_REGION = [33, 133]
    RIGHT_EYE_REGION = [263, 362]

    # Verify we have a reasonable number of landmarks
    if len(landmarks) < max(NOSE_TIP, LEFT_EYE, RIGHT_EYE, CHIN, FOREHEAD) + 1:
        # Not enough landmarks, so we cannot compute reliably.
        return False, (0.5, 0.5, 0), check_results

    try:
        key_points = [
            landmarks[NOSE_TIP],
            landmarks[LEFT_EYE],
            landmarks[RIGHT_EYE]
        ]
        # Optionally include additional points if available
        if len(landmarks) > CHIN:
            key_points.append(landmarks[CHIN])
        if len(landmarks) > FOREHEAD:
            key_points.append(landmarks[FOREHEAD])

        face_center_x = sum(pt['x'] for pt in key_points) / len(key_points)
        face_center_y = sum(pt['y'] for pt in key_points) / len(key_points)
        face_center_z = sum(pt['z'] for pt in key_points) / len(key_points)

        # Calculate z-difference between the eyes (used as an indicator for head rotation)
        z_diff = abs(landmarks[LEFT_EYE]['z'] - landmarks[RIGHT_EYE]['z'])
        z_diff_threshold = 0.03
        check_results["z_diff_too_high"] = z_diff > z_diff_threshold

        # Check if the eyes are horizontally level
        left_eye_y = sum(landmarks[i]['y'] for i in LEFT_EYE_REGION if i < len(landmarks)) / len(LEFT_EYE_REGION)
        right_eye_y = sum(landmarks[i]['y'] for i in RIGHT_EYE_REGION if i < len(landmarks)) / len(RIGHT_EYE_REGION)
        eye_level_diff = abs(left_eye_y - right_eye_y)
        eye_level_threshold = 0.03
        check_results["eyes_not_level"] = eye_level_diff > eye_level_threshold

        # Vertical boundary checks
        check_results["y_pos_too_low"] = face_center_y < 0.3
        check_results["y_pos_too_high"] = face_center_y > 0.7
        # Horizontal boundary check:
        check_results["too_far_side"] = (face_center_x < 0.25) or (face_center_x > 0.75)

    except Exception as e:
        print(f"Error in check_looking_at_screen: {e}")
        return False, (0.5, 0.5, 0), check_results

    # Decide if the person is looking at the screen.
    looking_away = (
            check_results["z_diff_too_high"] or
            check_results["y_pos_too_low"] or
            check_results["y_pos_too_high"] or
            check_results["too_far_side"] or
            check_results["eyes_not_level"]
    )
    is_looking = not looking_away

    print(f"Face center: ({face_center_x:.2f}, {face_center_y:.2f}, {face_center_z:.2f}), "
          f"Z-diff: {z_diff:.4f} (threshold: {z_diff_threshold}), Looking: {is_looking}")
    print(f"Orientation check details: {check_results}")

    return is_looking, (face_center_x, face_center_y, face_center_z), check_results


def check_movement(current_landmarks, prev_landmarks):
    """
    Calculate a movement score between consecutive frames using a subset of key landmarks.

    Args:
        current_landmarks (list): Landmarks for the current frame (flat list)
        prev_landmarks (list): Landmarks for the previous frame (flat list)

    Returns:
        float: Movement score scaled between 0.0 (no movement) and 1.0 (max movement)
    """
    try:
        # Define indices for landmarks that are expected to change noticeably with movement.
        KEY_LANDMARKS = [1, 4, 33, 61, 263, 291]
        # Use only indices that exist in both frames.
        indices = [i for i in KEY_LANDMARKS if i < len(current_landmarks) and i < len(prev_landmarks)]
        if len(indices) < 3:
            # Fallback: use as many as possible.
            indices = list(range(min(len(current_landmarks), len(prev_landmarks))))
        if not indices:
            return 0.0

        total_distance = 0.0
        for i in indices:
            curr_point = current_landmarks[i]
            prev_point = prev_landmarks[i]
            distance = ((curr_point['x'] - prev_point['x']) ** 2 +
                        (curr_point['y'] - prev_point['y']) ** 2 +
                        (curr_point['z'] - prev_point['z']) ** 2) ** 0.5
            total_distance += distance

        avg_distance = total_distance / len(indices)
        # Scale movement score (threshold can be adjusted)
        movement_score = min(1.0, avg_distance / 0.05)
        return movement_score

    except Exception as e:
        print(f"Error calculating movement: {e}")
        return 0.0
