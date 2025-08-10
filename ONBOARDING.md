# Onboarding System

GesahniV2 now includes a comprehensive onboarding system that guides new users through setting up their personalized AI assistant experience.

## Features

### 🎯 Multi-Step Onboarding Flow
- **Welcome Step**: Introduces users to GesahniV2's capabilities
- **Basic Info**: Collects personal information (name, email, timezone, language, occupation, location)
- **Preferences**: Customizes communication style, interests, and preferred AI model
- **Integrations**: Connects Gmail and Google Calendar for enhanced functionality
- **Completion**: Summary and getting started tips

### 🔧 Profile Management
- Persistent user profiles stored in the backend
- Settings page for updating preferences after onboarding
- Integration status tracking

### 🚀 Smart Routing
- Automatic redirect to onboarding for new users
- Skip options for optional steps
- Progress tracking and completion status

## Backend API

### Profile Endpoints
- `GET /v1/profile` - Get user profile
- `POST /v1/profile` - Update user profile
- `GET /v1/onboarding/status` - Get onboarding completion status
- `POST /v1/onboarding/complete` - Mark onboarding as completed

### Profile Schema
```typescript
interface UserProfile {
  name?: string;
  email?: string;
  timezone?: string;
  language?: string;
  communication_style?: string; // "casual", "formal", "technical"
  interests?: string[];
  occupation?: string;
  home_location?: string;
  preferred_model?: string; // "gpt-4o", "llama3", "auto"
  notification_preferences?: Record<string, any>;
  calendar_integration?: boolean;
  gmail_integration?: boolean;
  onboarding_completed?: boolean;
}
```

## Frontend Components

### Pages
- `/onboarding` - Main onboarding flow
- `/settings` - Profile and preferences management

### Components
- `OnboardingFlow` - Main flow controller
- `WelcomeStep` - Introduction and feature overview
- `BasicInfoStep` - Personal information collection
- `PreferencesStep` - AI preferences and communication style
- `IntegrationsStep` - Service connections (Gmail, Calendar)
- `CompleteStep` - Summary and completion

## User Experience

### Onboarding Flow
1. **Welcome**: Users see an overview of GesahniV2's capabilities
2. **Basic Info**: Required fields include name, with optional email, timezone, etc.
3. **Preferences**: Users choose communication style, interests, and AI model preference
4. **Integrations**: Optional connection to Gmail and Google Calendar
5. **Complete**: Summary of setup and getting started tips

### Settings Management
- Accessible via header link after login
- Full profile editing capabilities
- Real-time updates to backend
- Integration toggle controls

## Technical Implementation

### Data Storage
- User profiles stored in `app/memory/profile_store.py`
- JSON-based persistence with TTL caching
- Automatic hourly persistence to disk

### State Management
- React state for form data
- API integration for profile updates
- Local storage for session persistence

### Routing
- Automatic onboarding detection
- Redirect logic for incomplete onboarding
- Settings page access control

## Future Enhancements

### Planned Features
- [ ] Real Gmail/Calendar OAuth integration
- [ ] More integration options (Slack, Discord, etc.)
- [ ] Advanced preference controls
- [ ] Onboarding analytics and optimization
- [ ] A/B testing for onboarding flows

### Integration Opportunities
- [ ] Google OAuth for Gmail/Calendar
- [ ] Microsoft Graph for Outlook/Teams
- [ ] Slack API for workspace integration
- [ ] Discord API for server management

## Usage

### For Users
1. Register or login to GesahniV2
2. Complete the onboarding flow (required for first-time users)
3. Access settings anytime via the header link
4. Update preferences as needed

### For Developers
1. Profile data is available via the profile store
2. Onboarding status can be checked via API
3. New integration options can be added to the flow
4. Settings page can be extended with new fields

## Configuration

### Environment Variables
- `PROFILE_DB` - Path to profile storage file (default: `data/profiles.json`)
- `JWT_SECRET` - Required for user authentication
- `USERS_DB` - User database path

### Customization
- Modify onboarding steps in `OnboardingFlow.tsx`
- Add new profile fields in `UserProfile` interface
- Extend settings page with new sections
- Customize styling with Tailwind classes
