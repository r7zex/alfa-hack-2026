"""24 independent financial features; loan-form amounts are never substituted."""
from copy import deepcopy
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.operations import FinancialProfile
from ml.imported_lightgbm import FEATURE_NAMES, validate_features

# Synthetic 2022 reporting profile, not an observation from training data.
# Absolute reporting amounts are illustrative thousands of RUB; original training
# unit provenance is unavailable, so the score carries no business interpretation.
STABLE = dict(zip(FEATURE_NAMES, [1.8,203,38,55,.25,.9,1.4,8,18,12,14,55,120,2.2,1.8,45,6,0,18000,1600,10000,4500,900,4200]))
STRESSED = dict(zip(FEATURE_NAMES, [.5,730,180,270,.01,.25,.5,-4,-18,-3,-8,110,-300,-2,.9,90,2,1,8000,-600,12000,-800,30,8000]))
PROFILES={'synthetic_stable':STABLE,'synthetic_stressed':STRESSED}
PROVENANCE={'synthetic':True,'period':'2022','absolute_units':'illustrative thousands RUB',
            'ratios':'ratios; pct fields percentage points; days fields days; business_age years',
            'training_units_verified':False,'source':'fixed_delora_synthetic_profile_v1'}


class FinancialFeaturesProvider:
    async def collect(self, db: AsyncSession, business_id: int):
        profile=await db.get(FinancialProfile,business_id)
        if profile is None:
            return None, {'source':'absent','reason':'24 independent financial features are unavailable'}
        if profile.kind not in PROFILES and profile.kind!='verified':
            return None, {'source':'unsupported_profile'}
        frame=validate_features(profile.features)
        import math
        return {k:(float(v) if v is not None and math.isfinite(v) else None) for k,v in frame.iloc[0].items()},deepcopy(profile.provenance)
