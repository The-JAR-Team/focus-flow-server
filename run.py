from server.main.app import app

if __name__ == "__main__":
    print("Starting Flask development server...")
    app.run(host='0.0.0.0', port=5000)
