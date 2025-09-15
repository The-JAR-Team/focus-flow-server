# FocusFlow Server

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Badge"/>
  <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask Badge"/>
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL Badge"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Badge"/>
</p>

<p align="center">
  The backend server for <b>FocusFlow</b>, an AI-powered platform designed to turn passive video lectures into interactive, personalized learning experiences.
</p>

<p align="center">
  <a href="https://focusflow.art/focus-flow-client/"><strong>Live Site</strong></a> ·
  <a href="https://github.com/The-JAR-Team/focus-flow-client"><strong>Client Repo</strong></a> ·
  <a href="https://github.com/The-JAR-Team/focus-flow-models"><strong>Models Repo</strong></a>
</p>

---

## 🏆 Awards and Recognition

-   **🥇 1st Place, Best Poster** – The ACM SYSTOR 2025 Conference
-   **🥇 1st Place Winner** – The Annual Projects Conference at The Academic College of Tel Aviv-Yaffo
-   **🎤 Selected Presenter** – The International AI in Education (AIED) Conference 2025 as part of the Interactive Event

## 📐 Architecture & Data Flow

The FocusFlow architecture uses a client-heavy approach for real-time AI processing, allowing the server to focus on robust data management and content delivery.

1.  **Content Management**: Users create playlists with one of three privacy settings (Public, Unlisted, Private) and can add other users as subscribers to unlisted playlists.
2.  **AI-Powered Ingestion**: When a video is added, the server fetches its transcript and uses the **Google Gemini API** to pre-generate a full set of quizzes and summaries, which are then stored in the database.
3.  **Client-Side AI**: The engagement detection model (`.onnx` format) runs **entirely on the client's machine** for real-time, low-latency analysis.
4.  **Analytics Sync**: The client collects engagement data and sends it to the server in batches, where it's logged for user analytics.

## 🐳 Docker Deployment

The entire FocusFlow application (client, server, and database) can be run using Docker for a quick and easy setup.

| Service    | Docker Image                             | Command to Run                                  |
| :--------- | :--------------------------------------- | :---------------------------------------------- |
| **Database** | `somejon/focusflow-postgres`             | `docker run -p 5432:5432 somejon/focusflow-postgres` |
| **Server** | `somejon/focus-flow:latest`              | `docker pull somejon/focus-flow:latest`           |
| **Client** | `renanbazinin/focus-flow-client:latest`  | `docker pull renanbazinin/focus-flow-client:latest` |

---

## 🚀 Getting Started (Local Development)

Follow these instructions to run the server locally for development.

### **1. Prerequisites**
- Python 3.9+
- Docker
- Google Gemini API Key
- Google Account "App Password"

### **2. Clone the Repository**
```bash
git clone [https://github.com/The-JAR-Team/focus-flow-server.git](https://github.com/The-JAR-Team/focus-flow-server.git)
cd focus-flow-server
```

### **3. Launch the Database**
Start the pre-configured PostgreSQL container.
```bash
docker run -p 5432:5432 somejon/focusflow-postgres
```

### **4. Set Up Python Environment**
```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### **5. Configure Environment Variables**
Create a `.env` file in the root directory and populate it with your credentials.

```env
DB_HOST=localhost
DB_USER= # User from the Docker image
DB_PASSWORD= # Password from the Docker image
DB_NAME= # DB Name from the Docker image
DB_PORT=5432
GEMINI_API_KEY="your_gemini_api_key_here"
MODE=norm
GMAIL_SENDER_EMAIL="your_gmail_address@gmail.com"
GMAIL_APP_PASSWORD="your_gmail_app_password"
APP_CONFIRMATION_URL_BASE=http://localhost:5000
APP_CONFIRMATION_ENDPOINT=/api/confirm_email
SITE_LOGIN_URL= # URL to your frontend login page
PROXY_HTTP=http://<proxy_address>:<proxy_port>
PROXY_HTTPS=https://<proxy_address>:<proxy_port>
```

### **6. Run the Server**
```bash
flask run
```
The server is now live at `http://127.0.0.1:5000`.

---

## 📡 API Endpoints

A comprehensive list of API endpoints available on the server. All endpoints are prefixed with `/api`.

### Auth
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/register` | Register a new user account. |
| `POST` | `/login` | Authenticate a user and receive a session token. |
| `GET`  | `/confirm_email/{token}` | Confirm a user's email address. |
| `GET`  | `/validate_session` | Check if the current user's session is valid. |
| `POST` | `/logout` | Log out the current user. |

### User Info
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`  | `/user_info` | Get profile information for the logged-in user. |
| `POST` | `/update_user_info` | Update profile information for the logged-in user. |

### Playlists
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/playlists` | Create a new playlist. |
| `GET`  | `/playlists` | Get all playlists owned by the user. |
| `GET`  | `/playlists/{playlist_id}` | Get details for a specific playlist. |
| `PUT`  | `/playlists/{playlist_id}` | Update a playlist's details. |
| `DELETE`| `/playlists/{playlist_id}`| Delete a playlist. |

### Videos
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/videos/upload` | Add a new YouTube video to a specified playlist. |
| `GET`  | `/videos/accessible` | Get all videos accessible to the user (owned, public, subscribed). |
| `GET`  | `/videos/{youtube_id}/summary` | Get the AI-generated summary for a video. |
| `GET`  | `/videos/{youtube_id}/questions` | Get the AI-generated quiz questions for a video. |
| `DELETE`| `/videos/{video_id}` | Remove a video from a playlist. |

### Subscriptions
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/subscribe` | Add a user (by email) as a subscriber to one of the user's playlists. |
| `GET`  | `/playlist/{playlist_id}/subscribers` | Get a list of all subscribers for a playlist. |
| `DELETE`| `/unsubscribe` | Remove a subscriber from a playlist. |

### Groups
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/group` | Create a new group (a collection of playlists/videos). |
| `GET`  | `/group` | Get all groups owned by the user. |
| `DELETE`| `/group/{group_id}` | Delete a group. |
| `POST` | `/group/items` | Add an item (video/playlist) to a group. |
| `DELETE`| `/group/items` | Remove an item from a group. |

### Watch Data & Analytics
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/ticket/next` | Get a server ticket to start a watch session. |
| `POST` | `/watch/log_watch_batch` | Submit a batch of client-side engagement data to the server. |
| `GET`  | `/watch/get_results` | Retrieve engagement results for a completed session. |
| `GET`  | `/watch/results/user/{user_id}` | Get all watch results for a specific user. |
