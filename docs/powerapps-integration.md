# Power Apps Integration Guide

This document describes how to integrate the Azure RAG Chatbot API with Microsoft Power Apps and Power Automate.

## Overview

The RAG Chatbot API is designed to be easily consumable by Power Apps and Power Automate through:

- Stable JSON response format with consistent keys
- Always-present `citations` array (even when empty)
- Short `request_id` for troubleshooting
- Standard HTTP error codes
- Simple authentication via API key or Azure AD

## Endpoint Information

### Base URL

```
https://your-app-service.azurewebsites.net
```

### Chat Endpoint

| Property | Value |
|----------|-------|
| **URL** | `/chat` |
| **Method** | `POST` |
| **Content-Type** | `application/json` |
| **Authentication** | API Key or Azure AD Bearer Token |

## Authentication

### Option 1: API Key (Recommended for POC)

Include the API key in the `X-API-KEY` header:

```
X-API-KEY: your-api-key-here
```

### Option 2: Azure AD / Entra ID (Enterprise)

Include a Bearer token in the `Authorization` header:

```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIs...
```

## Request Format

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | Must be `application/json` |
| `X-API-KEY` | Conditional | Required if using API key authentication |
| `Authorization` | Conditional | Required if using Azure AD authentication |

### Request Body

```json
{
  "question": "What is the emergency shutdown procedure?",
  "session_id": "optional-session-id",
  "user_id": "optional-user-id",
  "manual_filter": "optional-manual-name.pdf"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | Yes | The user's question (1-2000 characters) |
| `session_id` | string | No | Session ID for conversation tracking |
| `user_id` | string | No | User ID for audit logging |
| `manual_filter` | string | No | Restrict search to a specific manual |

## Response Format

### Successful Response (200 OK)

```json
{
  "answer": "The emergency shutdown procedure involves pressing the red button on the control panel [Source 1]. You should then wait for the system to fully power down before proceeding [Source 2].",
  "citations": [
    {
      "manual_name": "Safety_Manual.pdf",
      "page": 45,
      "chunk_id": "safety-manual-p45-c1",
      "quote": "Press the red emergency button located on the main control panel..."
    },
    {
      "manual_name": "Operations_Guide.pdf",
      "page": 12,
      "chunk_id": "ops-guide-p12-c3",
      "quote": "Wait for complete system shutdown before proceeding with maintenance..."
    }
  ],
  "confidence": "high",
  "follow_up_question": null,
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### Response Fields

| Field | Type | Always Present | Description |
|-------|------|----------------|-------------|
| `answer` | string | Yes | The generated answer with source references |
| `citations` | array | Yes | List of citations (may be empty) |
| `confidence` | string | Yes | `"high"`, `"medium"`, or `"low"` |
| `follow_up_question` | string/null | Yes | Suggested follow-up or null |
| `request_id` | string | Yes | Unique ID for troubleshooting |

### Citation Object

| Field | Type | Description |
|-------|------|-------------|
| `manual_name` | string | Source PDF filename |
| `page` | integer | Page number (1-indexed) |
| `chunk_id` | string | Unique chunk identifier |
| `quote` | string | Short excerpt from the source |

## Error Responses

### 401 Unauthorized

Authentication failed.

```json
{
  "detail": "Missing X-API-KEY header"
}
```

or

```json
{
  "detail": "Invalid API key"
}
```

**Power Apps Handling**: Display "Please check your API key configuration" message.

### 422 Validation Error

Invalid request format.

```json
{
  "detail": [
    {
      "loc": ["body", "question"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**Power Apps Handling**: Display "Please enter a valid question" message.

### 429 Too Many Requests

Rate limit exceeded (if configured).

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

**Power Apps Handling**: Display "Service is busy. Please wait a moment and try again."

### 500 Internal Server Error

Server-side error.

```json
{
  "detail": "An error occurred while processing your request. Please try again."
}
```

**Power Apps Handling**: Display "Something went wrong. Please try again or contact support." Include the `request_id` if available for troubleshooting.

## Power Apps Custom Connector Setup

### 1. Create Custom Connector

1. Go to Power Apps > Data > Custom Connectors
2. Click "New custom connector" > "Create from blank"
3. Name: "RAG Chatbot"

### 2. Configure General Settings

- Host: `your-app-service.azurewebsites.net`
- Base URL: `/`
- Scheme: `HTTPS`

### 3. Configure Security

For API Key authentication:
- Authentication type: `API Key`
- Parameter label: `API Key`
- Parameter name: `X-API-KEY`
- Parameter location: `Header`

### 4. Define the Action

**Action Name**: `AskQuestion`

**Request**:
- Verb: `POST`
- URL: `/chat`
- Headers:
  - `Content-Type`: `application/json`
- Body:
```json
{
  "question": "@{triggerBody()?['question']}",
  "session_id": "@{triggerBody()?['session_id']}",
  "user_id": "@{triggerBody()?['user_id']}"
}
```

**Response**:
- Default response with schema from the response format above

### 5. Test the Connector

Use the Test tab to verify connectivity with a sample question.

## Power Automate Flow Example

### Simple Q&A Flow

```
Trigger: When a new message arrives (Teams/Email/etc.)
    |
    v
Action: RAG Chatbot - AskQuestion
    - question: triggerBody()?['message']
    - session_id: triggerBody()?['conversationId']
    - user_id: triggerBody()?['from']
    |
    v
Condition: Is confidence = "low"?
    |
    Yes --> Reply: "I couldn't find a confident answer. Here's what I found: [answer]"
    No  --> Reply: "[answer]"
    |
    v
Action: Send reply with citations
```

### Flow with Error Handling

```
Trigger: HTTP Request
    |
    v
Scope: Try
    |
    Action: RAG Chatbot - AskQuestion
    |
    v
Scope: Catch (Configure run after: has failed)
    |
    Condition: Status code = 401?
        Yes --> Response: "Authentication failed"
        No  --> Response: "Error occurred. Request ID: [request_id]"
```

## Power Apps Canvas App Example

### Basic Chat Interface

```
// On button click (Ask button)
Set(varLoading, true);
Set(varResponse, 
    RAGChatbot.AskQuestion({
        question: txtQuestion.Text,
        session_id: varSessionId,
        user_id: User().Email
    })
);
Set(varLoading, false);

// Display answer
If(
    !IsBlank(varResponse.answer),
    varResponse.answer,
    "No answer available"
)

// Display citations
ForAll(
    varResponse.citations,
    Concat(manual_name, " - Page ", Text(page))
)

// Show confidence indicator
Switch(
    varResponse.confidence,
    "high", Color.Green,
    "medium", Color.Yellow,
    "low", Color.Red
)
```

## Best Practices

### 1. Session Management

Always pass a consistent `session_id` for conversation tracking:

```
Set(varSessionId, If(IsBlank(varSessionId), GUID(), varSessionId))
```

### 2. Error Handling

Always handle errors gracefully:

```
If(
    IsError(varResponse),
    Notify("Unable to get answer. Please try again.", NotificationType.Error),
    // Process response
)
```

### 3. Loading States

Show loading indicators during API calls:

```
If(varLoading, 
    "Searching manuals...",
    varResponse.answer
)
```

### 4. Citation Display

Format citations for readability:

```
Concat(
    ForAll(varResponse.citations,
        manual_name & " (p. " & Text(page) & ")"
    ),
    ", "
)
```

### 5. Request ID for Support

Store and display request_id for troubleshooting:

```
"If you need help, reference ID: " & varResponse.request_id
```

## Rate Limiting Considerations

If rate limiting is enabled on the API:

1. Implement exponential backoff in Power Automate
2. Show user-friendly messages in Power Apps
3. Consider caching frequent questions

## Security Recommendations

1. **Store API keys securely** in Power Platform environment variables
2. **Use Azure AD authentication** for production deployments
3. **Implement user context** by passing user_id for audit trails
4. **Validate inputs** before sending to the API
5. **Log errors** with request_id for troubleshooting

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| 401 errors | Verify API key or Azure AD token |
| Empty citations | Question may not match manual content |
| Low confidence | Try rephrasing the question |
| Timeout errors | Check network connectivity |
| 500 errors | Contact support with request_id |

### Getting Help

When contacting support, always include:
- The `request_id` from the response
- The question that was asked
- The timestamp of the request
- Any error messages received
