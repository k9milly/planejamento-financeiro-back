/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // O tema é alternado por classe em <html>, não por prefers-color-scheme,
  // porque o usuário escolhe explicitamente no botão do cabeçalho.
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Escala derivada da paleta de referência do projeto: um roxo que vai
        // do cinza-lavanda claro ao quase-preto arroxeado.
        roxo: {
          50: '#f5f4f7',
          100: '#d8d8dc',
          200: '#b0a3c0',
          300: '#8d7799',
          400: '#6c5080',
          500: '#533d63',
          600: '#3d2b50',
          700: '#2c1f3b',
          800: '#22182f',
          900: '#161022',
          950: '#0f0d1a',
        },
      },
    },
  },
  plugins: [],
};
