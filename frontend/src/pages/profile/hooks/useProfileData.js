// frontend/src/pages/profile/hooks/useProfileData.js
// 프로필 데이터 로딩 및 상태 관리

import { useState, useEffect, useRef, useCallback } from 'react';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';

const DEFAULT_PROFILE = {
    name: '',
    status: '현역',
    position: '',
    regionMetro: '',
    regionLocal: '',
    electoralDistrict: '',
    bio: '',
    customTitle: '',
    targetElection: {
        position: '',
        regionMetro: '',
        regionLocal: '',
        electoralDistrict: '',
    },
    ageDecade: '',
    ageDetail: '',
    familyStatus: '',
    backgroundCareer: '',
    localConnection: '',
    politicalExperience: '',
    gender: '',
    committees: [''],
    customCommittees: [],
    constituencyType: '',
    slogan: '',
    sloganEnabled: false,
    donationInfo: '',
    donationEnabled: false,
};

const DEFAULT_BIO_ENTRIES = [
    {
        id: 'entry_initial',
        type: 'self_introduction',
        title: '자기소개 및 출마선언문',
        content: '',
        tags: [],
        weight: 1.0
    },
    {
        id: 'entry_additional_default',
        type: 'policy',
        title: '',
        content: '',
        tags: [],
        weight: 1.0
    }
];

export function useProfileData(user) {
    const [profile, setProfile] = useState(DEFAULT_PROFILE);
    const [bioEntries, setBioEntries] = useState(DEFAULT_BIO_ENTRIES);
    const [savedCustomTitle, setSavedCustomTitle] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const mountedRef = useRef(true);

    // 프로필 다시 불러오기
    const reloadProfile = useCallback(async () => {
        const res = await callFunctionWithNaverAuth('getUserProfile');
        const profileData = res?.profile || res || {};

        const newProfile = {
            name: profileData.name || profileData.displayName || '',
            status: profileData.status || '현역',
            position: profileData.position || '',
            regionMetro: profileData.regionMetro || '',
            regionLocal: profileData.regionLocal || '',
            electoralDistrict: profileData.electoralDistrict || '',
            bio: profileData.bio || '',
            customTitle: profileData.customTitle || '',
            targetElection: profileData.targetElection || {
                position: '', regionMetro: '', regionLocal: '', electoralDistrict: '',
            },
            ageDecade: profileData.ageDecade || '',
            ageDetail: profileData.ageDetail || '',
            familyStatus: profileData.familyStatus || '',
            backgroundCareer: profileData.backgroundCareer || '',
            localConnection: profileData.localConnection || '',
            politicalExperience: profileData.politicalExperience || '',
            gender: profileData.gender || '',
            committees: profileData.committees || [''],
            customCommittees: profileData.customCommittees || [],
            constituencyType: profileData.constituencyType || '',
            slogan: profileData.slogan || '',
            sloganEnabled: profileData.sloganEnabled || false,
            donationInfo: profileData.donationInfo || '',
            donationEnabled: profileData.donationEnabled || false,
        };

        setProfile(newProfile);

        // bioEntries 복원
        if (profileData.bioEntries && Array.isArray(profileData.bioEntries)) {
            setBioEntries(profileData.bioEntries);
        } else {
            const bioContent = newProfile.bio?.trim() || '';
            setBioEntries([
                { ...DEFAULT_BIO_ENTRIES[0], content: bioContent },
                { ...DEFAULT_BIO_ENTRIES[1] }
            ]);
        }

        setSavedCustomTitle(profileData.customTitle || '');

        // localStorage 동기화
        try {
            const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
            const updatedUser = { ...currentUser, ...newProfile, bio: profileData.bio || '' };
            localStorage.setItem('currentUser', JSON.stringify(updatedUser));
            window.dispatchEvent(new CustomEvent('userProfileUpdated', { detail: updatedUser }));
        } catch (e) {
            console.warn('ProfilePage: localStorage 업데이트 실패:', e);
        }

        return newProfile;
    }, []);

    // 필수 필드 누락 체크
    const checkMissingFields = useCallback((profileData) => {
        const missing = [];
        if (!profileData.position) missing.push('position');
        if (!profileData.regionMetro) missing.push('regionMetro');

        if (profileData.position === '기초자치단체장' && !profileData.regionLocal) {
            missing.push('regionLocal');
        } else if (profileData.position && profileData.position !== '광역자치단체장' && profileData.position !== '기초자치단체장') {
            if (!profileData.regionLocal) missing.push('regionLocal');
            if (!profileData.electoralDistrict) missing.push('electoralDistrict');
        }
        return missing;
    }, []);

    // 최초 로드
    useEffect(() => {
        mountedRef.current = true;

        (async () => {
            try {
                setLoading(true);
                await reloadProfile();
            } catch (e) {
                console.error('[getUserProfile 오류]', e);
                if (mountedRef.current) {
                    setError('프로필 정보를 불러오지 못했습니다: ' + (e.message || '알 수 없는 오류'));
                }
            } finally {
                if (mountedRef.current) setLoading(false);
            }
        })();

        return () => { mountedRef.current = false; };
    }, [reloadProfile]);

    const handleFieldChange = useCallback((name, value) => {
        setError('');
        setProfile(prev => ({ ...prev, [name]: value }));
    }, []);

    return {
        profile, setProfile,
        bioEntries, setBioEntries,
        savedCustomTitle,
        loading, error, setError,
        reloadProfile,
        handleFieldChange,
        checkMissingFields,
    };
}
