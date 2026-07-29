const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const CopyWebpackPlugin = require('copy-webpack-plugin');

module.exports = {
    entry: './src/index.js',
    output: {
        path: path.resolve(__dirname, 'dist'),
        filename: 'bundle.js',
    },
    target: 'electron-renderer',
    module: {
        rules: [
            {
                test: /\.(js|jsx)$/,
                exclude: /node_modules/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env', '@babel/preset-react']
                    }
                }
            },
            {
                test: /\.css$/,
                use: ['style-loader', 'css-loader']
            },
            {
                test: /\.(png|jpg|jpeg|gif|webp)$/i,
                type: 'asset/resource'
            }
        ]
    },
    resolve: {
        extensions: ['.js', '.jsx']
    },
    plugins: [
        new HtmlWebpackPlugin({
            template: './src/index.html',
            filename: 'index.html'
        }),
        // Task-battery audio (e.g. calibrated speech-in-noise files built by
        // tools/build_speech_in_noise_assets.py) is copied verbatim rather than
        // run through a JS/asset-resource loader: optimizedBatteryProfile.mjs
        // references these by plain relative URL string ('audio/<file>.wav') so
        // the same module stays loadable under plain `node --test`, which has
        // no loader for binary imports. noErrorOnMissing lets the build succeed
        // before any audio assets have been generated yet.
        new CopyWebpackPlugin({
            patterns: [
                { from: 'src/assets/audio', to: 'audio', noErrorOnMissing: true },
            ],
        }),
    ],
    devtool: 'source-map'
};
