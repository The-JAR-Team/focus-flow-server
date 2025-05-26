import os
from datetime import datetime, timedelta, timezone  # Added timezone

from simple_mailer import PasscodeLinkMailer, EmailSendingError, EmailSendingAuthError, EmailSendingConnectionError
import psycopg2.errors  # For specific error handling if needed

from db.DB import DB  # Assuming DB.py is in a 'db' subdirectory

# --- Constants ---
CONFIRMATION_VALIDITY_MINUTES = 10
EMAIL_SEND_DELAY_SECONDS = 3


def send_registration_confirmation_email(user_id: int, email: str, first_name: str, last_name: str):
    """
    Sends a registration confirmation email to the user.
    Stores the generated passcode and the current UTC timestamp in the Email_Confirmation table.
    """
    passcode_sent = None
    error_message = None

    gmail_sender = os.getenv("GMAIL_SENDER_EMAIL")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    app_confirmation_base_url = os.getenv("APP_CONFIRMATION_URL_BASE", "http://localhost:5000")
    app_confirmation_endpoint = os.getenv("APP_CONFIRMATION_ENDPOINT", "/confirm_email")
    app_confirmation_url = app_confirmation_base_url + app_confirmation_endpoint

    if not gmail_sender or not gmail_password:
        error_message = "Email server not configured (missing GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD)."
        print(f"TODO: {error_message}")
    else:
        try:
            full_name = f"{first_name} {last_name}"
            email_body_template_for_mailer = (
                f"<p>Hello {full_name},</p>"
                "<p>Thank you for registering! We're excited to have you.</p>"
                "<p>Please click the button below to confirm your email address and activate your account. "
                "This link is valid for {validity_duration}.</p>"
            )

            mailer = PasscodeLinkMailer(
                sender_email=gmail_sender,
                gmail_app_password=gmail_password,
                subject="Welcome! Please Confirm Your Email",
                message_body_template=email_body_template_for_mailer,
                valid_for_duration_seconds=CONFIRMATION_VALIDITY_MINUTES * 60,
                confirmation_link_base=app_confirmation_url
            )

            passcode = mailer.send(recipient_email=email, delay_seconds=EMAIL_SEND_DELAY_SECONDS)

            with DB.get_cursor() as cur:
                # Explicitly set created_at with Python's current UTC time
                created_at_now_utc = datetime.now(timezone.utc)
                cur.execute(
                    'INSERT INTO "Email_Confirmation" (passcode, user_id, timer, created_at) VALUES (%s, %s, %s, %s)',
                    (passcode, user_id, CONFIRMATION_VALIDITY_MINUTES, created_at_now_utc)
                )
            passcode_sent = passcode
            print(f"Confirmation email initiated for {email}. Passcode: {passcode}")

        except (EmailSendingError, EmailSendingAuthError, EmailSendingConnectionError) as mail_e:
            error_message = f"Failed to send confirmation email to {email}: {mail_e}"
            print(f"TODO: {error_message}")
        except Exception as e_generic:
            error_message = f"An unexpected error occurred during email confirmation for {email}: {e_generic}"
            print(f"TODO: {error_message}")

    return passcode_sent, error_message


def confirm_user_email(passcode_from_link: str):
    """
    Confirms a user's email based on the provided passcode.
    Activates the user if the passcode is valid and not expired.
    Uses UTC for all time comparisons.
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Confirmation failed"}
    http_status_code = 400

    try:
        with DB.get_cursor() as cur:
            cur.execute('SELECT user_id, timer, created_at FROM "Email_Confirmation" WHERE passcode = %s',
                        (passcode_from_link,))
            record = cur.fetchone()

            if not record:
                response_dict["reason"] = "Invalid or expired confirmation code."
                http_status_code = 404
            else:
                user_id_to_activate, validity_minutes, created_at_ts_from_db = record

                # Ensure created_at_ts_from_db is in UTC.
                if created_at_ts_from_db.tzinfo is None:
                    created_at_utc = created_at_ts_from_db.replace(tzinfo=timezone.utc)
                    print(
                        f"TODO: Warning - created_at timestamp for passcode {passcode_from_link} was naive. Assuming UTC.")
                else:
                    created_at_utc = created_at_ts_from_db.astimezone(timezone.utc)

                # This is the selected block, using datetime.now(timezone.utc) for current time
                now_utc = datetime.now(timezone.utc)
                expiration_time_utc = created_at_utc + timedelta(minutes=validity_minutes)

                if now_utc > expiration_time_utc:
                    response_dict["reason"] = "Confirmation code has expired."
                    http_status_code = 410
                    cur.execute('DELETE FROM "Email_Confirmation" WHERE passcode = %s', (passcode_from_link,))
                else:
                    cur.execute(
                        'UPDATE "User" SET active = TRUE WHERE user_id = %s AND active = FALSE RETURNING user_id',
                        (user_id_to_activate,)
                    )
                    updated_user = cur.fetchone()

                    if updated_user:
                        cur.execute('DELETE FROM "Email_Confirmation" WHERE passcode = %s', (passcode_from_link,))
                        response_dict = {"status": "success",
                                         "message": "Email confirmed successfully. Your account is now active."}
                        http_status_code = 200
                    else:
                        cur.execute('SELECT active FROM "User" WHERE user_id = %s', (user_id_to_activate,))
                        user_status_row = cur.fetchone()
                        if user_status_row and user_status_row[0] is True:
                            response_dict = {"status": "success", "message": "Account already active."}
                            http_status_code = 200
                            cur.execute('DELETE FROM "Email_Confirmation" WHERE passcode = %s', (passcode_from_link,))
                        else:
                            response_dict["reason"] = "Failed to activate account. User not found or other issue."
                            http_status_code = 500
    except Exception as e:
        print(f"TODO: Error during email confirmation for passcode {passcode_from_link}: {e}")
        response_dict["reason"] = "An internal error occurred during confirmation."
        http_status_code = 500

    return response_dict, http_status_code


def handle_inactive_user_login_attempt(user_id: int):
    """
    Handles a login attempt by a user whose 'active' flag is FALSE.
    If their original confirmation window is still open, their account is deleted.
    Otherwise, informs them the confirmation period expired.
    Uses UTC for all time comparisons.
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Account inactive."}
    http_status_code = 403

    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT passcode, timer, created_at FROM "Email_Confirmation" WHERE user_id = %s ORDER BY created_at DESC LIMIT 1',
                (user_id,))
            confirmation_record = cur.fetchone()

            if confirmation_record:
                passcode, validity_minutes, created_at_ts_from_db = confirmation_record

                if created_at_ts_from_db.tzinfo is None:
                    created_at_utc = created_at_ts_from_db.replace(tzinfo=timezone.utc)
                    print(
                        f"TODO: Warning - created_at timestamp for user {user_id} confirmation was naive. Assuming UTC.")
                else:
                    created_at_utc = created_at_ts_from_db.astimezone(timezone.utc)

                # Using datetime.now(timezone.utc) for current time
                now_utc = datetime.now(timezone.utc)
                expiration_time_utc = created_at_utc + timedelta(minutes=validity_minutes)

                if now_utc > expiration_time_utc:
                    cur.execute('DELETE FROM "Email_Confirmation" WHERE passcode = %s', (passcode,))
                    cur.execute('DELETE FROM "User" WHERE user_id = %s', (user_id,))
                    response_dict = {
                        "status": "failed",
                        "reason": "Account not activated. Your registration has been removed as the confirmation window was still open. Please register again."
                    }
                    http_status_code = 410
                else:
                    response_dict = {
                        "status": "failed",
                        "reason": "The Account is not activated. Please confirm your email to activate your account."
                    }
                    http_status_code = 403
            else:
                cur.execute('DELETE FROM "User" WHERE user_id = %s', (user_id,))
                response_dict = {
                    "status": "failed",
                    "reason": "Account didnt activate in time, and was deleted, please register again."
                }
    except Exception as e:
        print(f"TODO: Error in handle_inactive_user_login_attempt for user_id {user_id}: {e}")
        response_dict = {"status": "failed", "reason": "Server error handling inactive account."}
        http_status_code = 500

    return response_dict, http_status_code
