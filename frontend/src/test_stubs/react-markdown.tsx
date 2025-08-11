import React from 'react';

type Props = { children?: React.ReactNode } & Record<string, unknown>;

export default function ReactMarkdownStub({ children }: Props) {
  return <div data-testid="react-markdown">{children}</div>;
}

import React from 'react';
export default function ReactMarkdown({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>;
}


