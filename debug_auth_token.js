// Debug script to set authentication token in browser localStorage
// Run this in the browser console to set the token for testing

const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0dXNlciIsInVzZXJfaWQiOiJ0ZXN0dXNlciIsImV4cCI6MTc1NTY2MjI5NiwianRpIjoiOTg3OTI4MTliYTYxNDc3ODhlYzk4NzYxMjg2OWNmMGQiLCJ0eXBlIjoiYWNjZXNzIiwic2NvcGVzIjpbImNhcmU6cmVzaWRlbnQiLCJtdXNpYzpjb250cm9sIl19.eMi0UgDny1efnC6bNDYT8EsMGNxSbU0GqmLQhIug9_c";

// Set the token in localStorage
localStorage.setItem("auth:access", token);

// Also set the auth epoch to trigger a refresh
localStorage.setItem("auth:epoch", Date.now().toString());

console.log("✅ Authentication token set in localStorage");
console.log("Token:", token);
console.log("You can now try sending a message in the chat");

// Trigger auth refresh by dispatching the auth epoch event
window.dispatchEvent(new Event('auth:epoch_bumped'));

// Optional: Reload the page to ensure the auth state is properly initialized
// window.location.reload();
