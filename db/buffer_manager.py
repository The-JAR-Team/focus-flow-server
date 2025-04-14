import json
from db.DB import DB


class BufferManager:
    @staticmethod
    def store_frame(user_id, youtube_id, video_time, extraction_payload):
        """
        Stores landmarks in the buffer and properly removes old frames.

        Args:
            user_id: User identifier
            youtube_id: YouTube video identifier
            video_time: Video playback time (seconds)
            extraction_payload: Contains landmarks data

        Returns:
            dict: Buffer information
        """
        # Extract just the landmarks from the payload
        landmarks = extraction_payload.get("landmarks", [])
        fps = extraction_payload.get("fps", 10)
        timestamp = extraction_payload.get("timestamp", 0)

        with DB.get_cursor() as cursor:
            # Store just the landmarks
            cursor.execute(
                """
                INSERT INTO frame_buffers 
                (user_id, youtube_id, timestamp, video_time, frame_data)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, youtube_id, timestamp, video_time, json.dumps(landmarks))
            )

            # Get frame count and ids ordered by timestamp
            cursor.execute(
                """
                SELECT id, timestamp FROM frame_buffers 
                WHERE user_id = %s AND youtube_id = %s
                ORDER BY timestamp DESC
                """,
                (user_id, youtube_id)
            )
            frames = cursor.fetchall()
            count = len(frames)

            # Calculate how many frames we need for 10 seconds
            frames_needed = fps * 10

            # If we have more frames than needed, delete the oldest ones
            if count > frames_needed:
                # Get IDs of frames to delete (all except the newest frames_needed)
                frames_to_keep = frames[:frames_needed]
                keep_ids = [frame[0] for frame in frames_to_keep]

                # Delete all frames except those in keep_ids
                cursor.execute(
                    """
                    DELETE FROM frame_buffers
                    WHERE user_id = %s AND youtube_id = %s
                    AND id NOT IN %s
                    """,
                    (user_id, youtube_id, tuple(keep_ids))
                )

                # Log deletion results
                deleted_count = cursor.rowcount
                print(f"Deleted {deleted_count} old frames, keeping {len(keep_ids)} frames")

                # Get updated count
                count = len(keep_ids)

        return {
            "frame_count": count,
            "frames_needed": frames_needed
        }

    @staticmethod
    def get_frames_for_processing(user_id, youtube_id):
        """
        Get the landmarks for processing.

        Args:
            user_id: User identifier
            youtube_id: YouTube video identifier

        Returns:
            tuple: (landmarks_list, fps, frame_count) or (None, None, frame_count)
        """
        with DB.get_cursor() as cursor:
            # Get frame count
            cursor.execute(
                "SELECT COUNT(*) FROM frame_buffers WHERE user_id = %s AND youtube_id = %s",
                (user_id, youtube_id)
            )
            count = cursor.fetchone()[0]
            print(count)
            # Assuming fps of 10 if not specified elsewhere
            fps = 10
            frames_needed = fps * 10

            # If we don't have enough frames, return None
            if count < frames_needed:
                return None, fps, count

            # Get the landmarks, ordered by timestamp
            cursor.execute(
                """
                SELECT frame_data
                FROM frame_buffers
                WHERE user_id = %s AND youtube_id = %s
                ORDER BY timestamp ASC
                LIMIT %s
                """,
                (user_id, youtube_id, frames_needed)
            )
            rows = cursor.fetchall()

            # Extract landmarks from frames
            landmarks_list = []
            for row in rows:
                landmarks = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                landmarks_list.append(landmarks)

            return landmarks_list, fps, count

    @staticmethod
    def clear_buffer(user_id, youtube_id):
        """
        Clears all frames in the buffer for a specific user and video.

        Args:
            user_id: User identifier
            youtube_id: YouTube video identifier

        Returns:
            int: Number of frames deleted
        """
        with DB.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM frame_buffers WHERE user_id = %s AND youtube_id = %s",
                (user_id, youtube_id)
            )
            deleted_count = cursor.rowcount
        return deleted_count
