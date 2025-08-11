/** @type {import('jest').Config} */
module.exports = {
    testEnvironment: 'jest-environment-jsdom',
    verbose: false,
    roots: ['<rootDir>/src'],
    setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
    moduleNameMapper: {
        '^@/(.*)$': '<rootDir>/src/$1',
        '^react-markdown$': '<rootDir>/src/test_stubs/react-markdown.tsx',
        '^remark-gfm$': '<rootDir>/src/test_stubs/remark-gfm.ts',
    },
    transform: {
        '^.+\\.(ts|tsx)$': ['ts-jest', { tsconfig: '<rootDir>/tsconfig.jest.json' }],
        '^.+\\.(js|jsx)$': ['ts-jest', { tsconfig: '<rootDir>/tsconfig.jest.json' }],
    },
    moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
    extensionsToTreatAsEsm: ['.ts', '.tsx'],
    transformIgnorePatterns: [
        // Transform ESM-only markdown libs
        '/node_modules/(?!(react-markdown|remark-gfm)/)'
    ],
};


