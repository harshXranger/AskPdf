# import os
# import json
# import unittest
# from unittest.mock import patch, MagicMock
# import numpy as np

# # Add backend directory to sys.path
# import sys
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# from app import (
#     app,
#     get_gemini_api_key,
#     get_configured_model,
#     get_gemini_model,
#     set_active_working_model,
#     mask_credential,
#     validate_gemini_key,
#     list_available_gemini_models,
#     get_candidate_models,
#     _parse_gemini_error,
#     _gemini_generate_once,
#     stream_gemini_answer,
# )


# class TestGeminiConfig(unittest.TestCase):
#     """Test environment variable loading, model defaults, and precedence rules."""

#     def test_gemini_api_key_primary(self):
#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyTestKey123456789", "GOOGLE_API_KEY": ""}):
#             self.assertEqual(get_gemini_api_key(), "AIzaSyTestKey123456789")

#     def test_google_api_key_fallback(self):
#         with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "AIzaSyFallbackKey98765"}):
#             self.assertEqual(get_gemini_api_key(), "AIzaSyFallbackKey98765")

#     def test_precedence_gemini_over_google(self):
#         with patch.dict(os.environ, {
#             "GEMINI_API_KEY": "AQ.Ab8PrimaryGeminiKey12345",
#             "GOOGLE_API_KEY": "AIzaSySecondaryGoogleKey54321"
#         }):
#             self.assertEqual(get_gemini_api_key(), "AQ.Ab8PrimaryGeminiKey12345")

#     def test_model_configuration_default(self):
#         with patch.dict(os.environ, {}, clear=True):
#             self.assertEqual(get_configured_model(), "gemini-3.8-flash")

#     def test_model_configuration_override(self):
#         with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.5-flash"}):
#             self.assertEqual(get_configured_model(), "gemini-3.5-flash")

#     def test_model_configuration_strips_models_prefix(self):
#         with patch.dict(os.environ, {"GEMINI_MODEL": "models/gemini-3.8-flash"}):
#             self.assertEqual(get_configured_model(), "gemini-3.8-flash")

#     def test_model_configuration_intercepts_deprecated_models(self):
#         with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash"}):
#             self.assertEqual(get_configured_model(), "gemini-3.8-flash")


# class TestCredentialValidation(unittest.TestCase):
#     """Test safe credential validation for all supported and unsupported key formats."""

#     def test_valid_aiza_key(self):
#         ok, msg = validate_gemini_key("AIzaSyD-mocked-valid-gemini-key-12345")
#         self.assertTrue(ok)
#         self.assertEqual(msg, "ok")

#     def test_valid_aq_key(self):
#         # ok, msg = validate_gemini_key("")
#         self.assertTrue(ok)
#         self.assertEqual(msg, "ok")

#     def test_missing_key(self):
#         ok, msg = validate_gemini_key("")
#         self.assertFalse(ok)
#         self.assertIn("not set", msg)

#     def test_oauth_user_token_rejected(self):
#         ok, msg = validate_gemini_key("ya29.a0AfH6SMCx_mock_oauth_access_token_12345")
#         self.assertFalse(ok)
#         self.assertIn("OAuth access or refresh token was supplied", msg)

#     def test_oauth_refresh_token_rejected(self):
#         ok, msg = validate_gemini_key("1//0gMock_refresh_token_string_example_12345")
#         self.assertFalse(ok)
#         self.assertIn("OAuth access or refresh token was supplied", msg)

#     def test_bearer_prefix_rejected(self):
#         ok, msg = validate_gemini_key("Bearer ya29.a0AfH6SMCx_token")
#         self.assertFalse(ok)
#         self.assertIn("OAuth access or refresh token was supplied", msg)

#     def test_key_with_whitespace_rejected(self):
#         ok, msg = validate_gemini_key("AIzaSyD test with spaces 12345")
#         self.assertFalse(ok)
#         self.assertIn("whitespace", msg)

#     def test_key_too_short_rejected(self):
#         ok, msg = validate_gemini_key("shortkey")
#         self.assertFalse(ok)
#         self.assertIn("too short", msg)

#     def test_mask_credential(self):
#         # self.assertEqual(mask_credential(""), "AQ.A...5Bfw")
#         self.assertEqual(mask_credential("AIzaSyD1234567890"), "AIza...7890")
#         self.assertEqual(mask_credential(""), "(empty)")
#         self.assertEqual(mask_credential("123"), "***")


# class TestDynamicModelDiscovery(unittest.TestCase):
#     """Test official Gemini API model listing and candidate ordering."""

#     @patch("app.requests.get")
#     def test_list_available_gemini_models_success(self, mock_get):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.json.return_value = {
#             "models": [
#                 {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
#                 {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
#                 {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]},  # Filtered out (TTS)
#                 {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},  # Filtered out (not generateContent)
#             ]
#         }
#         mock_get.return_value = mock_resp

#         models = list_available_gemini_models("AQ.MockKey123456789", force_refresh=True)
#         self.assertIn("gemini-3.8-flash", models)
#         self.assertIn("gemini-3.5-flash", models)
#         self.assertNotIn("gemini-3.8-flash-tts", models)
#         self.assertNotIn("embedding-001", models)

#     @patch("app.requests.get")
#     def test_list_available_gemini_models_api_failure_fallback(self, mock_get):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 500
#         mock_get.return_value = mock_resp

#         models = list_available_gemini_models("AQ.MockKey123456789", force_refresh=True)
#         self.assertTrue(len(models) > 0)
#         self.assertIn("gemini-3.5-flash", models)

#     def test_candidate_models_sequence(self):
#         with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.8-flash"}):
#             candidates = get_candidate_models()
#             self.assertEqual(candidates[0], "gemini-3.8-flash")
#             self.assertIn("gemini-3.5-flash", candidates)


# class TestGeminiErrorParsing(unittest.TestCase):
#     """Test detailed, non-leaking HTTP error parsing and avoid self-referential model messages."""

#     def test_error_parsing_401_invalid_key(self):
#         resp = MagicMock()
#         resp.status_code = 401
#         resp.json.return_value = {
#             "error": {
#                 "code": 401,
#                 "message": "API key not valid. Please pass a valid API key.",
#                 "status": "UNAUTHENTICATED",
#                 "details": [{"reason": "API_KEY_INVALID"}]
#             }
#         }
#         msg = _parse_gemini_error(resp, "gemini-3.8-flash")
#         self.assertIn("Invalid or expired Gemini API key", msg)

#     def test_error_parsing_401_oauth_unsupported(self):
#         resp = MagicMock()
#         resp.status_code = 401
#         resp.json.return_value = {
#             "error": {
#                 "code": 401,
#                 "message": "API key not valid.",
#                 "status": "UNAUTHENTICATED",
#                 "details": [{"reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED"}]
#             }
#         }
#         msg = _parse_gemini_error(resp, "gemini-3.8-flash")
#         self.assertIn("OAuth token passed where an API key is required", msg)

#     def test_error_parsing_403_permission_denied(self):
#         resp = MagicMock()
#         resp.status_code = 403
#         resp.json.return_value = {
#             "error": {
#                 "code": 403,
#                 "message": "Generative Language API has not been used in project...",
#                 "status": "PERMISSION_DENIED"
#             }
#         }
#         msg = _parse_gemini_error(resp, "gemini-3.8-flash")
#         self.assertIn("permission denied", msg.lower())

#     def test_error_parsing_404_model_not_found(self):
#         resp = MagicMock()
#         resp.status_code = 404
#         resp.json.return_value = {
#             "error": {
#                 "code": 404,
#                 "message": "models/gemini-2.5-flash is no longer available",
#                 "status": "NOT_FOUND"
#             }
#         }
#         msg = _parse_gemini_error(resp, "gemini-2.5-flash")
#         self.assertIn("gemini-2.5-flash", msg)
#         self.assertIn("not available or has been deprecated", msg)
#         # Verify it does NOT contain the buggy self-referential hardcoded string
#         self.assertNotIn("update GEMINI_MODEL to a supported model such as 'gemini-2.5-flash'", msg)

#     def test_error_parsing_503_high_demand(self):
#         resp = MagicMock()
#         resp.status_code = 503
#         resp.json.return_value = {
#             "error": {
#                 "code": 503,
#                 "message": "This model is currently experiencing high demand.",
#                 "status": "UNAVAILABLE"
#             }
#         }
#         msg = _parse_gemini_error(resp, "gemini-3.8-flash")
#         self.assertIn("high demand", msg)
#         self.assertIn("Automatic fallback", msg)

#     def test_error_parsing_429_quota(self):
#         resp = MagicMock()
#         resp.status_code = 429
#         resp.json.return_value = {
#             "error": {
#                 "code": 429,
#                 "message": "Resource exhausted",
#                 "status": "RESOURCE_EXHAUSTED"
#             }
#         }
#         msg = _parse_gemini_error(resp, "gemini-3.8-flash")
#         self.assertIn("quota exceeded", msg)


# class TestModelFallbackAndAPICalls(unittest.TestCase):
#     """Test automatic fallback from unavailable to healthy model and text generation."""

#     @patch("app.requests.post")
#     def test_automatic_fallback_on_404_or_503(self, mock_post):
#         # First call (gemini-3.8-flash) returns 503 high demand
#         # Second call (gemini-3.5-flash) returns 200 OK
#         resp_503 = MagicMock()
#         resp_503.status_code = 503
#         resp_503.json.return_value = {"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}}

#         resp_200 = MagicMock()
#         resp_200.status_code = 200
#         resp_200.json.return_value = {
#             "candidates": [
#                 {"content": {"parts": [{"text": "Dynamic fallback answer successful."}]}}
#             ]
#         }

#         mock_post.side_effect = [resp_503, resp_200]

#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345", "GEMINI_MODEL": "gemini-3.8-flash"}):
#             text, err = _gemini_generate_once("What is the capital of France?", "France context")
#             self.assertIsNone(err)
#             self.assertEqual(text, "Dynamic fallback answer successful.")
#             # Verify that two attempts took place (primary model -> fallback)
#             self.assertEqual(mock_post.call_count, 2)

#     @patch("app.requests.post")
#     def test_gemini_generate_once_direct_success(self, mock_post):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.json.return_value = {
#             "candidates": [
#                 {"content": {"parts": [{"text": "Paris is the capital of France."}]}}
#             ]
#         }
#         mock_post.return_value = mock_resp

#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345"}):
#             text, err = _gemini_generate_once("What is the capital of France?", "France context")
#             self.assertIsNone(err)
#             self.assertEqual(text, "Paris is the capital of France.")
#             call_kwargs = mock_post.call_args[1]
#             self.assertEqual(call_kwargs["headers"]["x-goog-api-key"], "AQ.Ab8MockKeyValidFormat12345")

#     @patch("app.requests.post")
#     def test_stream_gemini_answer_with_fallback(self, mock_post):
#         # First model returns 404 (deprecated), second model streams 200 OK
#         resp_404 = MagicMock()
#         resp_404.status_code = 404
#         resp_404.json.return_value = {"error": {"code": 404, "message": "Deprecated", "status": "NOT_FOUND"}}

#         resp_200 = MagicMock()
#         resp_200.status_code = 200
#         resp_200.iter_lines.return_value = [
#             'data: {"candidates": [{"content": {"parts": [{"text": "Streaming "}]}}]}',
#             "",
#             'data: {"candidates": [{"content": {"parts": [{"text": "fallback answer."}]}}]}',
#             "data: [DONE]"
#         ]

#         mock_post.side_effect = [resp_404, resp_200]

#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345"}):
#             chunks = list(stream_gemini_answer("Hello", "Context"))
#             self.assertEqual("".join(chunks), "Streaming fallback answer.")

#     def test_stream_gemini_answer_missing_key(self):
#         with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
#             chunks = list(stream_gemini_answer("Hello", "Context"))
#             self.assertEqual(len(chunks), 1)
#             self.assertIn("GEMINI_API_KEY is not set", chunks[0])


# class TestEndpointsAndRAG(unittest.TestCase):
#     """Test Flask routes, /models endpoint, and RAG pipeline with mock data."""

#     def setUp(self):
#         self.client = app.test_client()

#     def test_health_endpoint(self):
#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345"}):
#             resp = self.client.get("/health")
#             self.assertEqual(resp.status_code, 200)
#             data = resp.get_json()
#             self.assertEqual(data["status"], "ok")
#             self.assertTrue(data["gemini_configured"])
#             self.assertTrue(data["gemini_key_valid"])
#             self.assertEqual(data["gemini_model_configured"], "gemini-3.8-flash")

#     @patch("app.list_available_gemini_models")
#     def test_models_endpoint(self, mock_list):
#         mock_list.return_value = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest"]
#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345"}):
#             resp = self.client.get("/models")
#             self.assertEqual(resp.status_code, 200)
#             data = resp.get_json()
#             self.assertTrue(data["ok"])
#             self.assertIn("gemini-3.8-flash", data["available_models"])
#             self.assertEqual(data["configured_model"], "gemini-3.8-flash")

#     @patch("app._gemini_generate_once")
#     def test_test_key_endpoint_success(self, mock_gen):
#         mock_gen.return_value = ("Test connection successful", None)
#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345"}):
#             resp = self.client.get("/test-key")
#             self.assertEqual(resp.status_code, 200)
#             data = resp.get_json()
#             self.assertTrue(data["ok"])
#             self.assertEqual(data["response"], "Test connection successful")

#     def test_ask_endpoint_empty_question(self):
#         resp = self.client.post("/ask", json={"question": ""})
#         self.assertEqual(resp.status_code, 400)
#         self.assertIn("Question is required", resp.get_json()["error"])

#     @patch("app.load_latest_vector_store")
#     @patch("app.stream_gemini_answer")
#     def test_ask_endpoint_rag_success(self, mock_stream, mock_store):
#         mock_index = MagicMock()
#         mock_index.search.return_value = (np.array([[0.95]]), np.array([[0]]))
#         mock_chunks = ["AskPDF is a RAG chatbot for querying PDF documents."]
#         mock_payload = {"chunk_pages": [1]}
#         mock_store.return_value = (mock_index, mock_chunks, mock_payload)

#         mock_stream.return_value = iter(["AskPDF is ", "a chatbot."])

#         with patch.dict(os.environ, {"GEMINI_API_KEY": "AQ.Ab8MockKeyValidFormat12345"}):
#             resp = self.client.post("/ask", json={"question": "What is AskPDF?"})
#             self.assertEqual(resp.status_code, 200)
#             lines = resp.data.decode("utf-8").split("\n")
#             meta = json.loads(lines[0])
#             self.assertEqual(meta.get("source"), "Page 1")
#             content = "".join(lines[1:])
#             self.assertEqual(content, "AskPDF is a chatbot.")


# if __name__ == "__main__":
#     unittest.main()
