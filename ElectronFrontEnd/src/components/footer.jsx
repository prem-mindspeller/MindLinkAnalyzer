import React from 'react';

const Footer = () => {
    return (
        <footer className="app-footer">
            <p>Mindlink Analyzer v1.0.0 | &copy; <span id="current-year">{new Date().getFullYear()}</span> Mindspeller</p>
        </footer>
    );
}

export default Footer;