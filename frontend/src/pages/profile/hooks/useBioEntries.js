// frontend/src/pages/profile/hooks/useBioEntries.js
// Bio 엔트리 CRUD 및 카테고리 관리

import { useCallback } from 'react';
import { BIO_ENTRY_TYPES, BIO_CATEGORIES, VALIDATION_RULES } from '../../../constants/bio-types';

export function useBioEntries(bioEntries, setBioEntries, setProfile, setError) {

    // Bio 엔트리 변경 핸들러
    const handleBioEntryChange = useCallback((index, field, value) => {
        setBioEntries(prev => prev.map((entry, i) =>
            i === index ? { ...entry, [field]: value } : entry
        ));
        // 첫 번째 엔트리(자기소개)면 기존 bio 필드도 동기화
        if (index === 0 && field === 'content') {
            setProfile(prev => ({ ...prev, bio: value }));
        }
        setError('');
    }, [setBioEntries, setProfile, setError]);

    // 기존 bio 필드 변경 (호환성)
    const handleBioChange = useCallback((e) => {
        const { value } = e.target;
        setError('');
        setProfile(prev => ({ ...prev, bio: value }));
        setBioEntries(prev => prev.map((entry, index) =>
            index === 0 ? { ...entry, content: value } : entry
        ));
    }, [setProfile, setBioEntries, setError]);

    // 카테고리별 엔트리 필터링
    const getEntriesByCategory = useCallback((category) => {
        const categoryConfig = BIO_CATEGORIES[category];
        if (!categoryConfig) return [];
        return bioEntries.filter(entry =>
            categoryConfig.types.some(type => type.id === entry.type)
        );
    }, [bioEntries]);

    // Bio 엔트리 추가
    const addBioEntry = useCallback((category = 'PERFORMANCE') => {
        if (bioEntries.length >= VALIDATION_RULES.maxEntries) {
            setError(`최대 ${VALIDATION_RULES.maxEntries}개의 엔트리까지 추가 가능합니다.`);
            return;
        }

        const defaultType = category === 'PERSONAL' ? 'vision' : 'policy';
        const newEntry = {
            id: `entry_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            type: defaultType,
            title: '',
            content: '',
            tags: [],
            weight: 1.0
        };

        setBioEntries(prev => [...prev, newEntry]);
    }, [bioEntries.length, setBioEntries, setError]);

    // Bio 엔트리 삭제
    const removeBioEntry = useCallback((index) => {
        if (index === 0) {
            setError('자기소개 및 출마선언문은 삭제할 수 없습니다.');
            return;
        }
        setBioEntries(prev => prev.filter((_, i) => i !== index));
    }, [setBioEntries, setError]);

    return {
        handleBioEntryChange,
        handleBioChange,
        getEntriesByCategory,
        addBioEntry,
        removeBioEntry,
    };
}
