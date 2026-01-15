const fs = require('fs');
const path = require('path');
const { fetchElectoralDistrictList } = require('./services/district-sync');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const SG_ID_2024_GENERAL = '20240410'; // 2024 General Election (22nd)

async function extract2024Data() {
    console.log('🚀 Extracting 2024 General Election Data to JSON...');

    const result = {
        electionId: SG_ID_2024_GENERAL,
        electionName: '제22대 국회의원선거',
        timestamp: new Date().toISOString(),
        data: {}
    };

    // General Election types:
    // 2: 국회의원 (Member of Parliament)
    // 7: 비례대표국회의원 (Proportional MP) - usually just one nationwide district, but verifying.
    const types = [
        { code: '2', name: 'parliament' },
        { code: '7', name: 'proportional_parliament' }
    ];

    try {
        for (const t of types) {
            console.log(`📥 Fetching ${t.name} (${t.code})...`);
            const items = await fetchElectoralDistrictList(SG_ID_2024_GENERAL, t.code);
            result.data[t.name] = items;
            console.log(`   - Found ${items.length} records.`);
        }

        const outputPath = path.join(__dirname, '..', '2024_general_election.json');
        fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
        console.log(`\n✅ Data saved to ${outputPath}`);
    } catch (error) {
        console.error('❌ Extraction failed:', error);
    }
}

extract2024Data();
