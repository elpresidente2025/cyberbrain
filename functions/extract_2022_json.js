const fs = require('fs');
const path = require('path');
const { fetchElectoralDistrictList, fetchElectionList, fetchGusigunList } = require('./services/district-sync');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const SG_ID_2022_LOCAL = '20220601'; // 2022 Local Election ID

async function extract2022Data() {
    console.log('🚀 Extracting 2022 Local Election Data to JSON...');

    const result = {
        electionId: SG_ID_2022_LOCAL,
        electionName: '제8회 전국동시지방선거',
        timestamp: new Date().toISOString(),
        data: {}
    };

    // 1. Define types to fetch
    // Local Election relevant types: 
    // 3: 광역단체장 (Metro Governor/Mayor)
    // 4: 기초단체장 (Local Mayor)
    // 5: 광역의원 (Metro Councilor)
    // 6: 기초의원 (Local Councilor)
    // (2: General Election is not typical for Local, but sometimes by-elections happen. Focusing on 3,4,5,6)
    const types = [
        { code: '3', name: 'metro_head' }, // 광역단체장
        { code: '4', name: 'local_head' }, // 기초단체장
        { code: '5', name: 'metro_council' }, // 광역의원
        { code: '6', name: 'local_council' }  // 기초의원
    ];

    try {
        for (const t of types) {
            console.log(`📥 Fetching ${t.name} (${t.code})...`);
            const items = await fetchElectoralDistrictList(SG_ID_2022_LOCAL, t.code);
            result.data[t.name] = items;
            console.log(`   - Found ${items.length} records.`);
        }

        const outputPath = path.join(__dirname, '..', '2022_local_election.json');
        fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
        console.log(`\n✅ Data saved to ${outputPath}`);
    } catch (error) {
        console.error('❌ Extraction failed:', error);
    }
}

extract2022Data();
