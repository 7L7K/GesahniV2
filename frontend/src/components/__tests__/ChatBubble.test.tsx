import React from 'react';
import { render, screen } from '@testing-library/react';
import ChatBubble from '../ChatBubble';

describe('ChatBubble', () => {
    test('renders user message plainly', () => {
        render(<ChatBubble role="user" text="Hello" />);
        expect(screen.getByText('Hello')).toBeInTheDocument();
    });

    test('renders assistant markdown without rehypeRaw', () => {
        render(<ChatBubble role="assistant" text={"**bold** <script>alert('x')</script>"} />);
        // since react-markdown is stubbed, we assert raw text appears as literal
        expect(screen.getByText(/\*\*bold\*\*/)).toBeInTheDocument();
        expect(document.querySelector('script')).toBeNull();
    });

    test('injects tooltips for chunk refs and strips sources block', () => {
        const text = `Here [#chunk:abc123]\n\n\`\`\`sources\n- (abc123) Example snippet\n\`\`\``;
        render(<ChatBubble role="assistant" text={text} />);
        const el = screen.getByText('[#chunk:abc123]');
        expect(el).toBeInTheDocument();
        expect(el.getAttribute('title')).toMatch(/Example snippet/);
        expect(screen.queryByText('```sources')).not.toBeInTheDocument();
    });
});
