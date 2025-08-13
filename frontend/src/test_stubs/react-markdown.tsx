import React from 'react';

export default function ReactMarkdown({ children }: { children?: React.ReactNode }) {
  return <div data-testid="react-markdown">{children}</div>;
}


