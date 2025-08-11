import type { Config } from 'tailwindcss'

const config: Config = {
    content: [
        './src/app/**/*.{ts,tsx}',
        './src/components/**/*.{ts,tsx}',
        './src/hooks/**/*.{ts,tsx}',
    ],
    theme: {
        extend: {
            colors: {
                bg: 'var(--color-bg)',
                surface: 'var(--color-surface)',
                text: 'var(--color-text)',
                muted: 'var(--color-muted)',
                primary: 'var(--color-primary)',
                danger: 'var(--color-danger)',
            },
            borderRadius: {
                sm: 'var(--radius-sm)',
                md: 'var(--radius-md)',
                lg: 'var(--radius-lg)',
            },
            boxShadow: {
                1: 'var(--shadow-1)',
                2: 'var(--shadow-2)',
            },
            transitionDuration: {
                fast: 'var(--dur-fast)',
                base: 'var(--dur-base)',
            },
        },
    },
    plugins: [],
}

export default config


