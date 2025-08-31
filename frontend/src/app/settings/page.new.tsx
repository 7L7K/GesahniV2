import dynamic from 'next/dynamic';
import SettingsLoading from './SettingsLoading';

// Dynamically import the heavy settings component
const SettingsPageInner = dynamic(() => import('./SettingsPageInner'), {
    loading: () => <SettingsLoading />,
    ssr: false, // Disable SSR for this component as it uses browser-only APIs
});

export default function SettingsPage() {
    return <SettingsPageInner />;
}
