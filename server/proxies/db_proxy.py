def proxy_logins_api(api_function, payload, mode="norm"):
    """
    Calls the provided api_function with payload.
    - If the API call returns a success (HTTP 200), returns its response.
    - If not:
       * In mode "ignore", returns a dummy success response.
       * In any other mode, returns an error response with HTTP 400.
    Parameters:
      api_function (function): A function such as login_user, register_user, or validate_session.
      payload (dict or str): The data to be passed to the API function.
      mode (str): "ignore" or "norm"/"debug"
    Returns:
      tuple: (response_dict, http_status_code, session_id)
    """
    try:
        result = api_function(payload)
        # If the function returned only two items, add session_id from payload if it's a string.
        if len(result) == 2:
            response, status = result
            session_id = payload if isinstance(payload, str) else 0
        else:
            response, status, session_id = result

        if status == 200:
            return response, status, session_id
        else:
            if mode.lower() == "ignore":
                dummy_response = {"status": "success", "reason": ""}
                return dummy_response, status, session_id
            else:
                return {"status": "failed", "reason": response.get("reason", "API call failed")}, status, session_id
    except Exception as e:
        if mode.lower() == "ignore":
            dummy_response = {"status": "success", "reason": ""}
            return dummy_response, 200, 0
        else:
            return {"status": "failed", "reason": str(e)}, 400, 0
