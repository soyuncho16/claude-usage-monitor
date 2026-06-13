export default [
    {
        files: ['extension.js'],
        languageOptions: {
            ecmaVersion: 'latest',
            sourceType: 'module',
            globals: {
                globalThis: 'readonly',
                TextDecoder: 'readonly',
                TextEncoder: 'readonly',
                console: 'readonly',
                log: 'readonly',
                logError: 'readonly',
                print: 'readonly',
            },
        },
        rules: {
            'no-undef': 'error',
            'no-unused-vars': 'warn',
        },
    },
];
