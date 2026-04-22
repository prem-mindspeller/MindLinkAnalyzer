# Mindlink Analyzer - Electron + React Frontend

Modern desktop frontend for the BrainLink EEG Analysis System built with Electron and React.

## Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Development mode:**
   ```bash
   npm run build
   npm start
   ```

   Or for live reload during development:
   ```bash
   npm run electron-dev
   ```

3. **Production build:**
   ```bash
   npm run build
   npm start
   ```

## Project Structure

```
ElectronFrontEnd/
├── src/
│   ├── index.js          # React app entry point
│   ├── App.jsx           # Main React component
│   ├── index.html        # HTML template
│   └── styles/
│       └── main.css      # Global styles
├── dist/                 # Built files (generated)
├── main.js               # Electron main process
├── webpack.config.js     # Webpack configuration
└── package.json          # Dependencies
```

## Available Scripts

- `npm start` - Start Electron app
- `npm run dev` - Build React app in watch mode
- `npm run build` - Production build
- `npm run electron-dev` - Run both webpack and electron with live reload

## Next Steps

1. Add API integration (see BrainlinkReact/services/ApiService.js)
2. Implement device connection with Serial/Bluetooth
3. Add EEG visualization components
4. Create task execution screens
5. Implement results and analysis displays
