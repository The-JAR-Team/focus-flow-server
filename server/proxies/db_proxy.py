
def proxy_logins_api(api_function, payload, mode="norm"):
    """
    Calls the provided api_function with payload.
    - If the API call returns a success (HTTP 200), returns its response.
    - If not:
       * In mode "ignore", returns a dummy success response.
       * In any other mode, returns an error response with HTTP 400.

    Parameters:
      api_function (function): A function such as login_user, register_user, or validate_auth_token.
      payload (dict): The data to be passed to the API function.
      mode (str): "ignore" or "norm"/"debug"

    Returns:
      tuple: (response_dict, http_status_code)
    """
    try:
        response, status = api_function(payload)
        if status == 200:
            # API call succeeded; return its response.
            return response, status
        else:
            # API call failed.
            if mode.lower() == "ignore":
                dummy_response = {"status": "success", "reason": "", "auth_token": 123456}
                return dummy_response, status
            else:
                # Return an error; using 400 as per your specification.
                return {"status": "failed", "reason": response.get("reason", "API call failed"), "auth_token": 0}, status
    except Exception as e:
        # In case of an exception during the API call.
        if mode.lower() == "ignore":
            dummy_response = {"status": "success", "reason": "", "auth_token": 123456}
            return dummy_response, 200
        else:
            return {"status": "failed", "reason": str(e), "auth_token": 0}, 400

