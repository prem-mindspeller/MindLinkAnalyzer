# BrainLink Companion React Native App

A cross-platform mobile application for connecting to and monitoring BrainLink EEG devices, built with React Native and Expo.

## Features

- **Bluetooth Connectivity**: Connect to BrainLink EEG devices via Bluetooth Serial
- **Real-time Data Visualization**: Live EEG signal plotting and frequency band analysis
- **User Authentication**: JWT-based login with backend API integration
- **Device Authorization**: HWID validation for user-specific device access
- **Cross-platform**: Support for both iOS and Android devices
- **Environment Selection**: Switch between production and local API environments

## Technology Stack

- **React Native + Expo**: Cross-platform mobile development framework
- **react-native-bluetooth-serial**: Bluetooth device communication
- **react-native-chart-kit**: Real-time data visualization
- **AsyncStorage**: Local data persistence
- **JWT Authentication**: Secure user sessions

## Project Structure

```
BrainlinkReact/
├── components/                 # Reusable UI components
│   ├── EEGChart.js            # Real-time EEG signal chart
│   └── BandPowerDisplay.js    # Frequency band power visualization
├── screens/                   # Main application screens
│   ├── LoginScreen.js         # User authentication interface
│   └── DashboardScreen.js     # Device connection and monitoring
├── services/                  # External service integrations
│   ├── ApiService.js          # Backend API communication
│   └── BluetoothService.js    # Bluetooth device management
├── utils/                     # Utility functions
│   └── EEGProcessor.js        # EEG signal processing and analysis
├── constants/                 # App configuration
│   └── index.js              # Constants and configuration
└── App.js                    # Main application entry point
```

## Getting Started

### Prerequisites

- Node.js (v14 or higher)
- npm or yarn
- Expo CLI: `npm install -g @expo/cli`
- Android Studio (for Android development)
- Xcode (for iOS development, macOS only)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd BrainlinkReact
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Start the development server**
   ```bash
   npx expo start
   ```

4. **Run on device or simulator**
   - For Android: Press `a` in the terminal or scan QR code with Expo Go app
   - For iOS: Press `i` in the terminal or scan QR code with Expo Go app

### Development Setup

The project includes VS Code tasks for development:

- **Start Development Server**: Use Ctrl+Shift+P → "Tasks: Run Task" → "Start Expo Development Server"

## Configuration

### API Environments

The app supports multiple API environments configured in `constants/index.js`:

- **EN_PROD**: English production environment
- **NL_PROD**: Dutch production environment  
- **LOCAL**: Local development server (127.0.0.1:5000)

### EEG Processing

EEG signal processing parameters are configured in `constants/index.js`:

- **Sampling Rate**: 256 Hz (BrainLink standard)
- **Window Size**: 256 samples (1 second)
- **Frequency Bands**: Delta, Theta, Alpha, Beta, Gamma

### Bluetooth Configuration

Bluetooth settings are defined in `constants/index.js`:

- **Device Names**: Supported BrainLink device identifiers
- **Commands**: Device control commands
- **Connection Timeout**: 10 seconds

## Usage

### Login Process

1. Select the appropriate API environment (EN/NL/Local)
2. Enter your username and password
3. Tap "Login" to authenticate

### Device Connection

1. Ensure your BrainLink device is powered on and discoverable
2. Tap "Connect Device" to scan for available devices
3. The app will automatically validate device authorization
4. Once connected, real-time EEG data will be displayed

### Monitoring Features

- **Real-time EEG Signal**: Live waveform display
- **Frequency Band Analysis**: Power distribution across Delta, Theta, Alpha, Beta, and Gamma bands
- **Connection Status**: Visual indicator of device connection
- **Recording Control**: Start/stop data recording sessions

## API Integration

The app communicates with a backend API for:

- **User Authentication**: JWT token-based login
- **Device Validation**: HWID authorization checking
- **Session Data**: Upload and retrieve EEG session data
- **User Management**: Profile and statistics access

### API Endpoints

- `POST /auth/login` - User authentication
- `POST /auth/logout` - Session termination
- `GET /auth/validate` - Token validation
- `GET /users/{id}/hwids` - User authorized devices
- `POST /devices/validate` - Device HWID validation
- `POST /sessions` - Upload session data

## EEG Data Processing

The app includes comprehensive EEG signal processing:

- **Filtering**: High-pass and low-pass filtering for noise reduction
- **Artifact Detection**: Automatic detection of signal artifacts
- **Band Power Analysis**: Real-time frequency band power calculation
- **Signal Quality**: Continuous signal quality monitoring
- **Session Summary**: Statistical analysis of recording sessions

## Building for Production

### Android

1. **Configure signing**
   ```bash
   expo build:android
   ```

2. **Generate APK**
   ```bash
   eas build --platform android
   ```

### iOS

1. **Configure provisioning**
   ```bash
   expo build:ios
   ```

2. **Generate IPA**
   ```bash
   eas build --platform ios
   ```

## Troubleshooting

### Common Issues

1. **Bluetooth Connection Failed**
   - Ensure Bluetooth is enabled on device
   - Check that BrainLink device is in pairing mode
   - Verify device is not connected to another application

2. **Authentication Errors**
   - Verify API environment selection
   - Check network connectivity
   - Ensure username/password are correct

3. **Chart Not Displaying**
   - Verify device is connected and streaming data
   - Check console for data processing errors
   - Ensure sufficient data samples for visualization

### Debugging

Enable debugging mode by:
1. Opening the Expo development menu (shake device)
2. Selecting "Debug JS Remotely"
3. Checking browser console for detailed logs

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature/new-feature`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Contact the development team
- Check the troubleshooting section above

## Changelog

### v2.0.0
- Initial release
- Bluetooth connectivity for BrainLink devices
- Real-time EEG visualization
- User authentication and device authorization
- Cross-platform iOS and Android support
