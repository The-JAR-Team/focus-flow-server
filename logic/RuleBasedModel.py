from db.DB import DB


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
        # store_model_result(log_data_id, "RuleBasedModel", attention_score)

        return attention_score

    except Exception as e:
        print(f"Error in RuleBasedModel: {e}")
        return 0.5  # Default value in case of errors


def calculate_attention_score(landmarks, fps, interval):
    """
    Calculate attention score using a point-based system.

    Starting at 1.0, points are deducted for:
      - Missing face detection (0.3 of frame score)
      - Not looking at screen (full frame score)
      - Excessive movement (0.5 of frame score)

    The deduction per frame is weighted by a factor (point_value).

    Args:
        landmarks (list): List of frames (each frame a list of landmarks)
        fps (int): Frames per second
        interval (int): Time interval (in seconds)

    Returns:
        float: Final attention score between 0.0 and 1.0.
    """
    if not landmarks or fps == 0 or interval == 0:
        return 0.5  # Cannot compute properly

    total_frames = fps * interval
    # Default point value per frame
    point_value = 1.0 / total_frames if total_frames > 0 else 0.1

    # If you have very few frames, adjust the weighting so deductions are still meaningful.
    if len(landmarks) < 3:
        point_value = 0.5 / len(landmarks)
        print(f"Few frames detected, adjusting point value to {point_value:.4f}")

    score = 1.0
    prev_frame = None

    print(f"Starting attention calculation for {len(landmarks)} frames")
    print(f"Each frame is worth {point_value:.4f} points")

    for frame_idx, frame in enumerate(landmarks):
        # Extract the actual set of landmarks from the frame
        landmarks_in_frame = get_frame_landmarks(frame)
        print(f"Processing frame {frame_idx} with {len(landmarks_in_frame)} landmarks")

        # Check for empty data
        if not landmarks_in_frame or len(landmarks_in_frame) < 5:
            print(f"Frame {frame_idx}: Insufficient data, deducting points for missing detection")
            score -= 0.3 * point_value
            continue

        # Check if a face is detected (here we use a simple heuristic; you can adjust)
        face_detected = len(landmarks_in_frame) >= 5
        if not face_detected:
            print(f"Frame {frame_idx}: Face not detected properly, deducting 0.3 * frame value")
            score -= 0.3 * point_value
            continue

        # Check if the subject is looking at the screen.
        try:
            is_looking, face_center, check_results = check_looking_at_screen(landmarks_in_frame)
            if not is_looking:
                print(f"Frame {frame_idx}: Not looking at screen - {check_results}")
                score -= 1.0 * point_value
            # Calculate movement if previous frame exists
            if prev_frame is not None:
                movement = check_movement(landmarks_in_frame, get_frame_landmarks(prev_frame))
                print(f"Frame {frame_idx}: Movement score = {movement:.4f}")
                if movement > 0.2:
                    deduction = 0.5 * point_value
                    score -= deduction
                    print(f"Frame {frame_idx}: Excessive movement (-{deduction:.4f})")
            prev_frame = frame
        except Exception as e:
            print(f"Error processing frame {frame_idx}: {e}")
            score -= 0.3 * point_value

    final_score = max(0.0, min(1.0, score))
    print(f"Final attention score: {final_score:.4f}")
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


def store_model_result(log_data_id, model_name, result):
    """
    Store the model result in the database.

    Args:
        log_data_id (int): ID of the log data entry.
        model_name (str): Name of the model.
        result (float): Attention score.
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                '''INSERT INTO "Model_Result"
                   (log_data_id, model, result)
                   VALUES (%s, %s, %s)
                   RETURNING model_result_id''',
                (log_data_id, model_name, result)
            )
            model_result_id = cur.fetchone()[0]
            print(f"Stored model result with ID: {model_result_id}")
    except Exception as e:
        print(f"Error storing model result: {e}")
