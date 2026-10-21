/**
 * Static Firefox compatibility checks.
 *
 * These checks verify the extension metadata and native-messaging registration
 * that Firefox needs. They do not replace loading the extension in Firefox.
 */

import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const manifest = JSON.parse(
    readFileSync(new URL('./manifest.json', import.meta.url), 'utf8'),
);
const nativeManifest = JSON.parse(
    readFileSync(
        new URL('./native-host/com.hyprblocker.host.firefox.json', import.meta.url),
        'utf8',
    ),
);
const installer = readFileSync(new URL('../install.sh', import.meta.url), 'utf8');
const background = readFileSync(new URL('./background.js', import.meta.url), 'utf8');

describe('Firefox extension compatibility', () => {
    test('declares a stable Firefox extension ID and native messaging permission', () => {
        expect(manifest.browser_specific_settings?.gecko?.id).toBe(
            'hyprblocker@hyprblocker.local',
        );
        expect(manifest.permissions).toContain('nativeMessaging');
    });

    test('registers native messaging for the same Firefox extension ID', () => {
        expect(nativeManifest.name).toBe('com.hyprblocker.host');
        expect(nativeManifest.type).toBe('stdio');
        expect(nativeManifest.allowed_extensions).toEqual([
            manifest.browser_specific_settings.gecko.id,
        ]);
    });

    test('installer writes the Firefox native-messaging manifest', () => {
        expect(installer).toContain('FIREFOX_NATIVE_DIR="$HOME/.mozilla/native-messaging-hosts"');
        expect(installer).toContain('allowed_extensions');
        expect(installer).toContain('hyprblocker@hyprblocker.local');
    });

    test('background service worker recognizes Firefox', () => {
        expect(background).toContain("userAgent.includes('firefox')");
        expect(background).toContain("return 'firefox'");
    });
});
