const { onCall, HttpsError, onRequest } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');
const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');

// Base62 characters for short code generation
const CHARS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';

function generateCode(length = 6) {
    let result = '';
    for (let i = 0; i < length; i++) {
        result += CHARS.charAt(Math.floor(Math.random() * CHARS.length));
    }
    return result;
}

/**
 * Generate a short URL
 * Input: { originalUrl, postId, platform }
 */
exports.createShortUrl = wrap(async (req) => {
    const { originalUrl, postId, platform } = req.data || {};
    const { uid } = req.auth || {};

    if (!originalUrl) {
        throw new HttpsError('invalid-argument', 'Original URL is required');
    }

    // Check if a valid URL
    try {
        new URL(originalUrl);
    } catch (e) {
        throw new HttpsError('invalid-argument', 'Invalid URL format');
    }

    // Generate unique code (retry up to 3 times)
    let shortCode;
    let isUnique = false;
    let attempts = 0;

    while (!isUnique && attempts < 3) {
        shortCode = generateCode(6);
        const doc = await db.collection('short_links').doc(shortCode).get();
        if (!doc.exists) {
            isUnique = true;
        }
        attempts++;
    }

    if (!isUnique) {
        throw new HttpsError('resource-exhausted', 'Failed to generate unique code');
    }

    const shortLinkData = {
        originalUrl,
        shortCode,
        userId: uid || 'anonymous',
        postId: postId || null,
        platform: platform || null, // e.g., 'x', 'facebook'
        clicks: 0,
        createdAt: admin.firestore.FieldValue.serverTimestamp()
    };

    await db.collection('short_links').doc(shortCode).set(shortLinkData);

    // Construct the full short URL
    // Note: Function doesn't know the hosting domain automatically without config, 
    // but we can return the code and relative path.
    // The frontend can construct the full URL, or we can use a configured domain env var.
    // For now, return path.

    return ok({
        shortCode,
        shortUrlPath: `/s/${shortCode}`
    });
});

/**
 * Handle Short URL Redirect
 * HTTP Trigger (V2)
 */
exports.redirectShortUrl = onRequest({ cors: true }, async (req, res) => {
    // Path usually comes in as /s/CODE or /CODE depending on rewrite
    // We assume rewrite: /s/** -> redirectShortUrl
    // So path might be /s/CODE

    const pathParts = req.path.split('/').filter(p => p);
    const code = pathParts[pathParts.length - 1]; // Take the last part

    if (!code) {
        return res.status(404).send('Not Found');
    }

    try {
        const docRef = db.collection('short_links').doc(code);
        const doc = await docRef.get();

        if (!doc.exists) {
            return res.status(404).send('Link not found');
        }

        const data = doc.data();

        // Async increment click (don't await to speed up redirect? V2 might terminate?
        // Safer to await. It's just one write.)
        await docRef.update({
            clicks: admin.firestore.FieldValue.increment(1),
            lastClickedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        // Cache control for redirect? 
        // No, we want to track clicks, so don't cache too heavily or at browser level.
        res.set('Cache-Control', 'public, max-age=0, s-maxage=60'); // CDN cache short time

        return res.redirect(301, data.originalUrl);

    } catch (error) {
        console.error('Redirect error:', error);
        return res.status(500).send('Internal Server Error');
    }
});
