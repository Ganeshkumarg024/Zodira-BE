"""
Astrology Service for ZODIRA Backend

This service handles astrology chart calculations, API integrations,
and data processing for Vedic astrology features.
"""

import os
import json
import time
import logging
from datetime import datetime, date, time
from typing import Dict, List, Optional, Any, Tuple
from dateutil.relativedelta import relativedelta
import requests
import httpx

from app.config.settings import settings
from app.config.firebase import get_firestore_client
from app.config.settings import settings
from app.models.astrology import AstrologyChart, PlanetData, HouseData, DashaPeriod
from app.utils.astrology_utils import calculate_coordinates

logger = logging.getLogger(__name__)

class AstrologyService:
    """Service for handling astrology calculations and API integrations"""

    def __init__(self):
        self.free_astro_api_key = settings.free_astrology_api_key
        # FreeAstrology API endpoints (server-to-server upstream)
        self.api_endpoints = {
            "rasi": "https://json.freeastrologyapi.com/planets",
            "navamsa": "https://json.freeastrologyapi.com/navamsa-chart-info",
            "d10": "https://json.freeastrologyapi.com/d10-chart-info",
            # "chandra": "https://json.freeastrologyapi.com/chandra-kundali-info",
            "shadbala": "https://json.freeastrologyapi.com/shadbala/shadbala-summary",
            
            "planets_extended": "https://json.freeastrologyapi.com/planets/extended",
            "vimsottari": "https://json.freeastrologyapi.com/vimsottari/maha-dasas-and-antar-dasas"
        }
        self._db = None
        self._vimshottari_order = None

    @property
    def db(self):
        """Lazy initialization of Firestore client"""
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    @property
    def vimshottari_order(self):
        """Get Vimshottari Dasha order from database"""
        if self._vimshottari_order is None:
            self._vimshottari_order = self._get_or_init_vimshottari_order()
        return self._vimshottari_order

    def _normalize_birth_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and sanitize birth details for external API payloads (JSON-serializable only)"""
        d = details or {}

        # Extract date components
        year = d.get("year")
        month = d.get("month")
        day = d.get("date") or d.get("day")

        # Extract time components (support both hour/hours, minute/minutes, second/seconds)
        hour = d.get("hour", d.get("hours", 0)) or 0
        minute = d.get("minute", d.get("minutes", 0)) or 0
        second = d.get("second", d.get("seconds", 0)) or 0

        # Coerce numeric types
        try:
            year = int(year) if year is not None else None
            month = int(month) if month is not None else None
            day = int(day) if day is not None else None
        except Exception:
            pass

        try:
            hour = int(hour)
        except Exception:
            hour = 0
        try:
            minute = int(minute)
        except Exception:
            minute = 0
        try:
            second = int(second)
        except Exception:
            second = 0

        # Coordinates
        latitude = d.get("latitude", 20.5937)
        longitude = d.get("longitude", 78.9629)
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except Exception:
            latitude, longitude = 20.5937, 78.9629

        # Timezone normalization
        tz = d.get("timezone", 5.5)

        def _tz_offset(val):
            try:
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    s = val.strip()
                    lower = s.lower()
                    if lower in ("asia/kolkata", "asia/calcutta"):
                        return 5.5
                    # Accept "UTC+05:30", "+05:30", "-04:00", "5.5"
                    if lower.startswith(("utc", "gmt")):
                        lower = lower[3:]
                    sign = 1.0
                    if lower.startswith("+"):
                        lower = lower[1:]
                    elif lower.startswith("-"):
                        sign = -1.0
                        lower = lower[1:]
                    if ":" in lower:
                        h, m = lower.split(":", 1)
                        return sign * (float(int(h)) + float(int(m)) / 60.0)
                    return float(lower)
            except Exception:
                pass
            return 5.5

        timezone = _tz_offset(tz)

        return {
            "year": year,
            "month": month,
            "date": day,
            "hours": hour,
            "minutes": minute,
            "seconds": second,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
        }

    async def generate_astrology_chart(self, user_id: str, profile_id: str, birth_details: Dict[str, Any]) -> AstrologyChart:
        """
        Generate complete astrology chart for a user profile

        Args:
            user_id: User ID
            profile_id: Profile ID
            birth_details: Birth details dictionary

        Returns:
            AstrologyChart: Complete chart data
        """
        try:
            logger.info(f"Generating astrology chart for user {user_id}, profile {profile_id}")

            # Fetch all chart data
            chart_data = await self._fetch_all_charts(birth_details)

            # Persist raw chart parts for per-tab retrieval
            await self._save_chart_parts_to_db(user_id, profile_id, chart_data)
            
            # Calculate Vimshottari Dasha
            moon_longitude = self._extract_moon_longitude(chart_data.get("rasi", {}))
            birth_dt = birth_details.get("birth_datetime")
            if not isinstance(birth_dt, datetime):
                try:
                    y = int(birth_details.get("year"))
                    m = int(birth_details.get("month"))
                    d = int(birth_details.get("date") or birth_details.get("day"))
                    hh = int(birth_details.get("hour", birth_details.get("hours", 0)) or 0)
                    mm = int(birth_details.get("minute", birth_details.get("minutes", 0)) or 0)
                    ss = int(birth_details.get("second", birth_details.get("seconds", 0)) or 0)
                    birth_dt = datetime(y, m, d, hh, mm, ss)
                except Exception:
                    birth_dt = datetime.utcnow()
            vimshottari_dasha = self._compute_vimshottari_dasha(birth_dt, moon_longitude)

            # Structure the data
            structured_data = self._structure_astrology_data(
                chart_data.get("rasi", {}),
                chart_data.get("navamsa", {}),
                chart_data.get("d10", {}),
                chart_data.get("chandra", {}),
                chart_data.get("shadbala", {})
            )

            # Create chart object with proper datetime handling
            current_time = datetime.utcnow()
            chart = AstrologyChart(
                user_id=user_id,
                profile_id=profile_id,
                houses=structured_data["houses"],
                career=structured_data["career"],
                finance=structured_data["finance"],
                health=structured_data["health"],
                travel=structured_data["travel"],
                vimshottari_dasha=vimshottari_dasha,
                birth_details=birth_details,
                created_at=current_time,
                updated_at=current_time,
                is_active=True
            )

            # Save to database
            await self._save_chart_to_db(chart)

            logger.info(f"Successfully generated and saved astrology chart for user {user_id}")
            return chart

        except Exception as e:
            logger.error(f"Failed to generate astrology chart for user {user_id}: {e}")
            raise

    async def get_astrology_chart(self, user_id: str, profile_id: str) -> Optional[AstrologyChart]:
        """
        Retrieve astrology chart from database

        Args:
            user_id: User ID
            profile_id: Profile ID

        Returns:
            AstrologyChart or None if not found
        """
        try:
            doc_ref = self.db.collection('astrology_charts').document(f"{user_id}_{profile_id}")
            doc = doc_ref.get()

            if doc.exists:
                data = doc.to_dict()
                return AstrologyChart(**data)
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve astrology chart for user {user_id}: {e}")
            return None

    async def _fetch_all_charts(self, birth_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch all astrology charts from external API

        Args:
            birth_details: Birth details for API request

        Returns:
            Dict containing all chart data
        """
        charts_data = {}
        cache_dir = "cache/astrology"
        os.makedirs(cache_dir, exist_ok=True)

        for chart_type, url in self.api_endpoints.items():
            cache_file = os.path.join(cache_dir, f"{chart_type}_{birth_details['year']}_{birth_details['month']}_{birth_details['date']}.json")

            try:
                data = await self._fetch_chart_with_cache(url, birth_details, cache_file)
                charts_data[chart_type] = data
                logger.info(f"Successfully fetched {chart_type} chart")
            except Exception as e:
                logger.warning(f"Failed to fetch {chart_type} chart: {e}")
                charts_data[chart_type] = {}

        return charts_data

    async def _fetch_chart_with_cache(self, url: str, details: Dict[str, Any], cache_file: str) -> Dict[str, Any]:
        """
        Fetch chart data with caching mechanism

        Args:
            url: API endpoint URL
            details: Request payload
            cache_file: Cache file path

        Returns:
            Chart data dictionary
        """
        # Check cache first
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    logger.info(f"Loading {cache_file} from cache")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")

        # Fetch from API
        headers = {"x-api-key": self.free_astro_api_key}

        # Ensure only JSON-serializable payload is sent to external APIs
        payload = self._normalize_birth_details(details)
        try:
            log_keys = sorted(list(payload.keys()))
        except Exception:
            log_keys = list(payload.keys())
        logger.info(f"Calling astrology API {url} with payload keys: {log_keys}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                # Cache the result
                try:
                    with open(cache_file, "w") as f:
                        json.dump(data, f)
                    logger.info(f"Cached {cache_file}")
                except Exception as e:
                    logger.warning(f"Failed to cache {cache_file}: {e}")

                time.sleep(1)  # Rate limiting
                return data
            elif response.status_code == 429:
                raise Exception("Rate limit exceeded. Please try again later.")
            elif response.status_code == 403:
                raise Exception("Authentication failed. Check API key.")
            elif response.status_code == 404:
                raise Exception(f"Endpoint not found: {url}")
            else:
                raise Exception(f"API Error {response.status_code}: {response.text}")

    def _extract_moon_longitude(self, rasi_data: Dict[str, Any]) -> Optional[float]:
        """
        Extract Moon longitude from Rasi chart data (supporting multiple API response shapes)
        """
        try:
            # Shape A: {"output": [ { "<id>": { "name": "Moon", "fullDegree": ... }, ... } ]}
            if isinstance(rasi_data.get("output"), list) and rasi_data["output"]:
                maybe_map = rasi_data["output"][0]
                if isinstance(maybe_map, dict):
                    for item in maybe_map.values():
                        name = item.get("name") or item.get("planet") or item.get("Planet") or ""
                        if str(name).lower() == "moon":
                            val = item.get("fullDegree") or item.get("degree") or item.get("full_degree")
                            return float(val) if val is not None else None

            # Shape B: {"planets": [ {"name":"Moon","fullDegree":...}, ... ]} or dict
            planets = rasi_data.get("planets")
            if isinstance(planets, list):
                for item in planets:
                    name = item.get("name") or item.get("planet") or ""
                    if str(name).lower() == "moon":
                        val = item.get("fullDegree") or item.get("degree")
                        return float(val) if val is not None else None
            if isinstance(planets, dict):
                for item in planets.values():
                    name = item.get("name") or item.get("planet") or ""
                    if str(name).lower() == "moon":
                        val = item.get("fullDegree") or item.get("degree")
                        return float(val) if val is not None else None

            # Shape C: nested under "response" or "data" key
            resp = rasi_data.get("response") or rasi_data.get("data")
            if isinstance(resp, dict):
                return self._extract_moon_longitude(resp)

            return None
        except Exception as e:
            logger.error(f"Failed to extract Moon longitude: {e}")
            return None

    def _compute_vimshottari_dasha(self, birth_datetime: datetime, moon_longitude: Optional[float]) -> List[DashaPeriod]:
        """
        Compute Vimshottari Dasha periods

        Args:
            birth_datetime: Birth datetime
            moon_longitude: Moon longitude in degrees

        Returns:
            List of DashaPeriod objects
        """
        if moon_longitude is None:
            logger.warning("Moon longitude not available, using default for Dasha calculation")
            moon_longitude = 0

        nakshatra_size = 13.3333333
        # Derive nakshatra index from Moon's longitude (0..26), clamp to bounds
        nakshatra_index_raw = int(moon_longitude // nakshatra_size)
        if nakshatra_index_raw < 0:
            nakshatra_index_raw = 0
        elif nakshatra_index_raw > 26:
            nakshatra_index_raw = 26

        # Resolve Vimshottari order safely (9 lords repeating over 27 nakshatras)
        order = self.vimshottari_order or self._get_or_init_vimshottari_order()
        if not order:
            logger.warning("Vimshottari order unavailable, using fallback list")
            order = [
                ("Ketu", 7),
                ("Venus", 20),
                ("Sun", 6),
                ("Moon", 10),
                ("Mars", 7),
                ("Rahu", 18),
                ("Jupiter", 16),
                ("Saturn", 19),
                ("Mercury", 17),
            ]

        idx0 = nakshatra_index_raw % len(order)
        lord, full_years = order[idx0]

        nakshatra_start = nakshatra_index_raw * nakshatra_size
        nakshatra_progress = moon_longitude - nakshatra_start
        balance_fraction = (nakshatra_size - nakshatra_progress) / nakshatra_size
        balance_years = full_years * balance_fraction

        dasha_sequence = []
        current_time = birth_datetime

        # First Dasha (partial)
        dasha_end = current_time + relativedelta(years=int(balance_years),
                                                 months=int((balance_years % 1) * 12))
        dasha_sequence.append(DashaPeriod(
            planet=lord,
            start_date=current_time.strftime("%Y-%m-%d"),
            end_date=dasha_end.strftime("%Y-%m-%d"),
            start_age=round((current_time - birth_datetime).days / 365.25, 2),
            end_age=round((dasha_end - birth_datetime).days / 365.25, 2)
        ))
        current_time = dasha_end

        # Remaining Dashas
        order_index = idx0
        for i in range(1, len(order) * 12):
            order_index = (idx0 + i) % len(order)
            lord, full_years = order[order_index]
            dasha_end = current_time + relativedelta(years=full_years)

            dasha_sequence.append(DashaPeriod(
                planet=lord,
                start_date=current_time.strftime("%Y-%m-%d"),
                end_date=dasha_end.strftime("%Y-%m-%d"),
                start_age=round((current_time - birth_datetime).days / 365.25, 2),
                end_age=round((dasha_end - birth_datetime).days / 365.25, 2)
            ))

            current_time = dasha_end
            if (current_time - birth_datetime).days / 365.25 >= 120:
                break

        return dasha_sequence

    def _structure_astrology_data(self, rasi, navamsa, d10, chandra, shadbala) -> Dict[str, Any]:
        """
        Structure astrology data into organized format

        Args:
            rasi, navamsa, d10, chandra, shadbala: Chart data dictionaries

        Returns:
            Structured astrology data
        """
        structured = {
            "houses": {f"house_{i}": HouseData() for i in range(1, 13)},
            "career": {},
            "finance": {},
            "health": {},
            "travel": {}
        }

        # Process Rasi planets
        if rasi and rasi.get("output"):
            rasi_planets = rasi["output"][0]
            for planet_data in rasi_planets.values():
                house_num = planet_data.get("house_number") or planet_data.get("house")
                if house_num and 1 <= house_num <= 12:
                    planet = PlanetData(
                        name=planet_data.get("name"),
                        sign=planet_data.get("current_sign"),
                        degree=planet_data.get("fullDegree"),
                        strength=shadbala.get("output", {}).get(planet_data.get("name"), {}).get("Shadbala") if shadbala else None,
                        house_number=house_num,
                        current_sign=planet_data.get("current_sign"),
                        fullDegree=planet_data.get("fullDegree")
                    )
                    structured["houses"][f"house_{house_num}"].planets.append(planet)

        # Career data
        structured["career"] = {
            "10th_house_planets": structured["houses"]["house_10"].planets,
            "d10_summary": d10.get("output", {}),
            "strengths": shadbala.get("output", {}) if shadbala else {}
        }

        # Finance data
        structured["finance"] = {
            "2nd_house_planets": structured["houses"]["house_2"].planets,
            "11th_house_planets": structured["houses"]["house_11"].planets,
            "strengths": shadbala.get("output", {}) if shadbala else {}
        }

        # Health data
        structured["health"] = {
            "6th_house_planets": structured["houses"]["house_6"].planets,
            "8th_house_planets": structured["houses"]["house_8"].planets,
            "strengths": shadbala.get("output", {}) if shadbala else {}
        }

        # Travel data
        structured["travel"] = {
            "3rd_house_planets": structured["houses"]["house_3"].planets,
            "12th_house_planets": structured["houses"]["house_12"].planets,
            "strengths": shadbala.get("output", {}) if shadbala else {}
        }

        return structured

    def _get_or_init_vimshottari_order(self):
        """
        Get Vimshottari Dasha order from database, initialize if not exists

        Returns:
            List of tuples: [(planet_name, years), ...]
        """
        try:
            doc_ref = self.db.collection('astrology_config').document('vimshottari_order')
            doc = doc_ref.get()

            if doc.exists:
                data = doc.to_dict()
                order_data = data.get('order', [])
                # Convert back to tuple format for internal use; fallback to defaults if missing/invalid
                parsed = []
                if isinstance(order_data, list) and order_data:
                    if isinstance(order_data[0], dict):
                        # New format: list of dicts
                        try:
                            parsed = [(item.get('planet'), item.get('years')) for item in order_data if isinstance(item, dict)]
                        except Exception:
                            parsed = []
                    else:
                        # Old format: list of tuples (for backward compatibility)
                        parsed = order_data

                try:
                    if parsed and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in parsed):
                        return parsed
                except Exception:
                    pass

                # Fallback to default order if not present or invalid
                return [
                    ("Ketu", 7),
                    ("Venus", 20),
                    ("Sun", 6),
                    ("Moon", 10),
                    ("Mars", 7),
                    ("Rahu", 18),
                    ("Jupiter", 16),
                    ("Saturn", 19),
                    ("Mercury", 17),
                ]
            else:
                # Initialize with default values
                default_order = [
                    ("Ketu", 7),
                    ("Venus", 20),
                    ("Sun", 6),
                    ("Moon", 10),
                    ("Mars", 7),
                    ("Rahu", 18),
                    ("Jupiter", 16),
                    ("Saturn", 19),
                    ("Mercury", 17),
                ]

                # Convert to Firestore-compatible format (no nested arrays)
                firestore_order = [
                    {'planet': planet, 'years': years}
                    for planet, years in default_order
                ]
                doc_ref.set({
                    'order': firestore_order,
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                })

                logger.info("Initialized Vimshottari Dasha order in database")
                return default_order

        except Exception as e:
            logger.error(f"Failed to get Vimshottari order from database: {e}")
            # Fallback to hardcoded values
            fallback_order = [
                ("Ketu", 7),
                ("Venus", 20),
                ("Sun", 6),
                ("Moon", 10),
                ("Mars", 7),
                ("Rahu", 18),
                ("Jupiter", 16),
                ("Saturn", 19),
                ("Mercury", 17),
            ]
            logger.info("Using fallback Vimshottari order")
            return fallback_order

    async def _save_chart_to_db(self, chart: AstrologyChart) -> None:
        """
        Save astrology chart to Firestore

        Args:
            chart: AstrologyChart object to save
        """
        try:
            doc_id = f"{chart.user_id}_{chart.profile_id}"
            doc_ref = self.db.collection('astrology_charts').document(doc_id)
            chart.updated_at = datetime.utcnow()

            # Convert chart to dict with proper datetime handling
            try:
                if hasattr(chart, 'dict'):
                    chart_dict = chart.dict()
                else:
                    chart_dict = chart.__dict__

                # Convert datetime objects to strings with proper handling
                def convert_datetime(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    elif isinstance(obj, date):
                        return obj.isoformat()
                    elif isinstance(obj, time):
                        return obj.isoformat()
                    elif hasattr(obj, '__dict__'):
                        # Handle nested objects properly
                        if hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
                            return convert_datetime(obj.dict())
                        else:
                            return convert_datetime(obj.__dict__)
                    elif isinstance(obj, list):
                        return [convert_datetime(item) for item in obj]
                    elif isinstance(obj, dict):
                        return {key: convert_datetime(value) for key, value in obj.items()}
                    else:
                        return obj

                chart_dict = convert_datetime(chart_dict)
                doc_ref.set(chart_dict)
            except Exception as e:
                logger.error(f"Failed to save chart to database: {e}")
                # Save basic structure as fallback
                doc_ref.set({
                    'user_id': chart.user_id,
                    'profile_id': chart.profile_id,
                    'houses': {},
                    'career': {},
                    'finance': {},
                    'health': {},
                    'travel': {},
                    'vimshottari_dasha': [],
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat(),
                    'is_active': True
                })
            logger.info(f"Saved astrology chart {doc_id} to database")
        except Exception as e:
            logger.error(f"Failed to save astrology chart to database: {e}")
            raise

    def _chart_to_dict(self, chart: AstrologyChart) -> Dict[str, Any]:
        """Convert AstrologyChart to dictionary with proper datetime handling"""
        try:
            chart_dict = chart.dict() if hasattr(chart, 'dict') else chart.__dict__

            # Handle datetime serialization
            def convert_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, time):
                    return obj.isoformat()
                elif hasattr(obj, '__dict__'):
                    return self._chart_to_dict(obj)
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                elif isinstance(obj, dict):
                    return {key: convert_datetime(value) for key, value in obj.items()}
                else:
                    return obj

            return convert_datetime(chart_dict)
        except Exception as e:
            logger.error(f"Failed to convert chart to dict: {e}")
            # Return basic structure as fallback
            return {
                'user_id': chart.user_id,
                'profile_id': chart.profile_id,
                'houses': {},
                'career': {},
                'finance': {},
                'health': {},
                'travel': {},
                'vimshottari_dasha': [],
                'updated_at': datetime.utcnow().isoformat()
            }

    # Persist raw parts for Rasi/Navamsa/D10/Chandra/Shadbala
    async def _save_chart_parts_to_db(self, user_id: str, profile_id: str, parts: Dict[str, Any]) -> None:
        try:
            doc_id = profile_id
            doc_ref = self.db.collection('astrology_chart_parts').document(doc_id)

            # Preserve created_at if updating
            existing = doc_ref.get()
            created_at = None
            if existing.exists:
                try:
                    existing_data = existing.to_dict() or {}
                    created_at = existing_data.get('created_at')
                except Exception:
                    created_at = None

            def convert_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, time):
                    return obj.isoformat()
                elif hasattr(obj, '__dict__'):
                    try:
                        return convert_datetime(obj.__dict__)
                    except Exception:
                        return str(obj)
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                elif isinstance(obj, dict):
                    return {k: convert_datetime(v) for k, v in obj.items()}
                else:
                    return obj

            payload = {
                'user_id': user_id,
                'profile_id': profile_id,
                'rasi': convert_datetime(parts.get('rasi', {})),
                'navamsa': convert_datetime(parts.get('navamsa', {})),
                'd10': convert_datetime(parts.get('d10', {})),
                'chandra': convert_datetime(parts.get('chandra', {})),
                'shadbala': convert_datetime(parts.get('shadbala', {})),
                'updated_at': datetime.utcnow().isoformat()
            }
            if created_at:
                payload['created_at'] = created_at
            else:
                payload['created_at'] = datetime.utcnow().isoformat()

            doc_ref.set(payload)
            logger.info(f"Saved astrology chart parts for {doc_id}")
        except Exception as e:
            logger.error(f"Failed to save chart parts to database: {e}")
            # Do not raise; generation should continue

    async def get_chart_part(self, user_id: str, profile_id: str, chart_type: str) -> Optional[Dict[str, Any]]:
        try:
            chart_type = (chart_type or '').lower()
            valid = {'rasi', 'navamsa', 'd10', 'chandra', 'shadbala'}
            if chart_type not in valid:
                logger.warning(f"Invalid chart_type requested: {chart_type}")
                return None

            doc_id = profile_id
            doc_ref = self.db.collection('astrology_chart_parts').document(doc_id)
            doc = doc_ref.get()
            if not doc.exists:
                logger.info(f"Chart parts not found for {doc_id}")
                return None

            data = doc.to_dict() or {}
            return data.get(chart_type) or None
        except Exception as e:
            logger.error(f"Failed to get chart part {chart_type} for {user_id}_{profile_id}: {e}")
            return None

    async def generate_chart_part(self, user_id: str, profile_id: str, birth_details: Dict[str, Any], chart_type: str) -> Optional[Dict[str, Any]]:
        """
        Generate a single chart part (rasi, navamsa, d10, chandra, shadbala) and persist it.

        Args:
            user_id: User ID
            profile_id: Profile ID
            birth_details: Raw birth details (strings/ints acceptable) - normalized internally
            chart_type: One of rasi | navamsa | d10 | chandra | shadbala

        Returns:
            The fetched chart part data or None on failure
        """
        valid = {'rasi', 'navamsa', 'd10', 'chandra', 'shadbala'}
        ct = (chart_type or '').lower()
        if ct not in valid:
            raise ValueError(f"Invalid chart_type '{chart_type}', must be one of {sorted(list(valid))}")

        url = self.api_endpoints.get(ct)
        if not url:
            raise ValueError(f"No API endpoint configured for chart_type '{chart_type}'")

        # Build cache file path consistent with _fetch_all_charts
        cache_dir = "cache/astrology"
        os.makedirs(cache_dir, exist_ok=True)
        try:
            year = birth_details.get('year')
            month = birth_details.get('month')
            datev = birth_details.get('date') or birth_details.get('day')
        except Exception:
            year = month = datev = None
        cache_file = os.path.join(cache_dir, f"{ct}_{year}_{month}_{datev}.json")

        try:
            # Fetch the single chart part (payload normalization happens inside)
            data = await self._fetch_chart_with_cache(url, birth_details, cache_file)

            # Write/merge to Firestore chart parts doc
            doc_id = profile_id
            doc_ref = self.db.collection('astrology_chart_parts').document(doc_id)

            # Preserve created_at if updating
            existing = doc_ref.get()
            created_at = None
            if existing.exists:
                try:
                    existing_data = existing.to_dict() or {}
                    created_at = existing_data.get('created_at')
                except Exception:
                    created_at = None

            # Reuse serializer from _save_chart_parts_to_db
            def convert_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, time):
                    return obj.isoformat()
                elif hasattr(obj, '__dict__'):
                    try:
                        return convert_datetime(obj.__dict__)
                    except Exception:
                        return str(obj)
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                elif isinstance(obj, dict):
                    return {k: convert_datetime(v) for k, v in obj.items()}
                else:
                    return obj

            payload = {
                ct: convert_datetime(data),
                'updated_at': datetime.utcnow().isoformat()
            }
            if created_at:
                payload['created_at'] = created_at
            else:
                payload['created_at'] = datetime.utcnow().isoformat()

            # Merge update to keep other parts untouched
            doc_ref.set(payload, merge=True)
            logger.info(f"Saved single chart part '{ct}' for {doc_id}")
            return data
        except Exception as e:
            logger.error(f"Failed to generate chart part '{chart_type}' for {user_id}_{profile_id}: {e}")
            return None

    async def fetch_planets_extended(self, birth_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetch extended planetary details for dashboard:
        - planet name, position, zodiac sign, sign lord, house, nakshatra number/name/pada,
          nakshatra vimsottari lord, retrograde status.
        """
        try:
            url = self.api_endpoints.get("planets_extended")
            if not url:
                raise ValueError("planets_extended endpoint not configured")
            bd = self._normalize_birth_details(birth_details or {})
            cache_dir = "cache/astrology"
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(
                cache_dir,
                f"planets_extended_{bd.get('year')}_{bd.get('month')}_{bd.get('date')}.json"
            )
            data = await self._fetch_chart_with_cache(url, bd, cache_file)
            logger.info("Fetched planets_extended successfully")
            return data
        except Exception as e:
            logger.error(f"Failed to fetch planets_extended: {e}")
            return None

    async def fetch_vimsottari(self, birth_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetch Vimsottari maha-dasas and antar-dasas for dashboard storage.
        """
        try:
            url = self.api_endpoints.get("vimsottari")
            if not url:
                raise ValueError("vimsottari endpoint not configured")
            bd = self._normalize_birth_details(birth_details or {})
            cache_dir = "cache/astrology"
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(
                cache_dir,
                f"vimsottari_{bd.get('year')}_{bd.get('month')}_{bd.get('date')}.json"
            )
            data = await self._fetch_chart_with_cache(url, bd, cache_file)
            logger.info("Fetched vimsottari successfully")
            return data
        except Exception as e:
            logger.error(f"Failed to fetch vimsottari: {e}")
            return None

    async def save_dashboard_extras(
        self,
        user_id: str,
        profile_id: str,
        planets_extended: Optional[Dict[str, Any]],
        vimsottari: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Persist dashboard extras into Firestore:
        Collection: astrology_dashboard_extras
        Document:   {user_id}_{profile_id}
        Fields:     planets_extended, vimsottari, created_at, updated_at
        """
        try:
            doc_id = f"{user_id}_{profile_id}"
            doc_ref = self.db.collection('astrology_dashboard_extras').document(doc_id)

            # Preserve created_at if updating
            existing = doc_ref.get()
            created_at = None
            if existing.exists:
                try:
                    existing_data = existing.to_dict() or {}
                    created_at = existing_data.get('created_at')
                except Exception:
                    created_at = None

            def convert_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, time):
                    return obj.isoformat()
                elif hasattr(obj, '__dict__'):
                    try:
                        return convert_datetime(obj.__dict__)
                    except Exception:
                        return str(obj)
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                elif isinstance(obj, dict):
                    return {k: convert_datetime(v) for k, v in obj.items()}
                else:
                    return obj

            payload: Dict[str, Any] = {
                'user_id': user_id,
                'profile_id': profile_id,
                'updated_at': datetime.utcnow().isoformat()
            }
            if planets_extended is not None:
                payload['planets_extended'] = convert_datetime(planets_extended)
            if vimsottari is not None:
                payload['vimsottari'] = convert_datetime(vimsottari)
            if created_at:
                payload['created_at'] = created_at
            else:
                payload['created_at'] = datetime.utcnow().isoformat()

            doc_ref.set(payload, merge=True)
            logger.info(f"Saved dashboard extras for {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save dashboard extras: {e}")
            return False

    async def get_dashboard_extras(self, user_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve dashboard extras from Firestore.
        """
        try:
            doc_id = f"{user_id}_{profile_id}"
            doc_ref = self.db.collection('astrology_dashboard_extras').document(doc_id)
            doc = doc_ref.get()
            if not doc.exists:
                return None
            return doc.to_dict() or {}
        except Exception as e:
            logger.error(f"Failed to get dashboard extras for {user_id}_{profile_id}: {e}")
            return None

# Global service instance
astrology_service = AstrologyService()