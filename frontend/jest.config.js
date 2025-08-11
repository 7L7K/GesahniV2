/** @type {import('jest').Config} */
module.exports = {
    testEnvironment: 'jest-environment-jsdom',
    verbose: false,
    roots: ['<rootDir>/src'],
    setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
    moduleNameMapper: {
        '^@/(.*)$': '<rootDir>/src/$1',
    },
    transform: {
        '^.+\\.(ts|tsx)$': ['ts-jest', { tsconfig: '<rootDir>/tsconfig.json' }],
        '^.+\\.(js|jsx)$': 'ts-jest',
    },
    moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
    extensionsToTreatAsEsm: ['.ts', '.tsx'],
};


