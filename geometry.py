import math


# ============================================================
# WGS84 Ellipsoid
# ============================================================

WGS84_A_M = 6378137.0
WGS84_INV_F = 298.257223563
WGS84_F = 1.0 / WGS84_INV_F
WGS84_B_M = WGS84_A_M * (1.0 - WGS84_F)

VINCENTY_TOLERANCE_RAD = 1e-12
VINCENTY_MAX_ITERATIONS = 200


def normalize_bearing(angle_deg: float) -> float:
    if not math.isfinite(angle_deg):
        raise ValueError("angle_deg must be finite")

    return angle_deg % 360.0


def normalize_longitude(longitude_deg: float) -> float:
    if not math.isfinite(longitude_deg):
        raise ValueError("longitude_deg must be finite")

    return (longitude_deg + 180.0) % 360.0 - 180.0


def focal_length_px(
    frame_width: int,
    hfov_deg: float,
) -> float:

    if frame_width <= 0:
        raise ValueError(
            "frame_width must be > 0"
        )

    if (
        not math.isfinite(hfov_deg)
        or not 0.0 < hfov_deg < 180.0
    ):
        raise ValueError(
            "hfov_deg must be between 0 and 180"
        )

    return frame_width / (
        2.0
        * math.tan(
            math.radians(hfov_deg) / 2.0
        )
    )


def pixel_to_bearing(
    preset_bearing_deg: float,
    x_px: float,
    frame_width: int,
    hfov_deg: float,
    north_offset_deg: float = 0.0,
    principal_x_px: float | None = None,
) -> float:
    """
    Pinhole projection:
    pixel X -> angular offset -> bearing
    """

    if not math.isfinite(x_px):
        raise ValueError(
            "x_px must be finite"
        )

    cx = (
        frame_width / 2.0
        if principal_x_px is None
        else principal_x_px
    )

    fx = focal_length_px(
        frame_width,
        hfov_deg,
    )

    offset_deg = math.degrees(
        math.atan2(
            x_px - cx,
            fx,
        )
    )

    return normalize_bearing(
        preset_bearing_deg
        + north_offset_deg
        + offset_deg
    )


def gps_from_bearing_distance(
    camera_lat: float,
    camera_lon: float,
    distance_m: float,
    bearing_deg: float,
) -> tuple[float, float]:
    """
    Vincenty Direct Formula on WGS84 Ellipsoid.

    Direct Geodetic Problem:

        Start latitude/longitude
        + initial bearing
        + geodesic distance
        ->
        destination latitude/longitude

    The function signature remains compatible
    with the previous spherical implementation.
    """

    values = (
        camera_lat,
        camera_lon,
        distance_m,
        bearing_deg,
    )

    if not all(
        math.isfinite(v)
        for v in values
    ):
        raise ValueError(
            "All geolocation inputs must be finite"
        )

    if not -90.0 <= camera_lat <= 90.0:
        raise ValueError(
            "camera_lat must be between -90 and 90"
        )

    if distance_m < 0:
        raise ValueError(
            "distance_m must be >= 0"
        )

    if distance_m == 0:
        return (
            float(camera_lat),
            normalize_longitude(camera_lon),
        )

    # --------------------------------------------------------
    # WGS84 parameters
    # --------------------------------------------------------

    a = WGS84_A_M
    b = WGS84_B_M
    f = WGS84_F

    phi1 = math.radians(
        camera_lat
    )

    lambda1 = math.radians(
        normalize_longitude(camera_lon)
    )

    alpha1 = math.radians(
        normalize_bearing(bearing_deg)
    )

    sin_alpha1 = math.sin(alpha1)
    cos_alpha1 = math.cos(alpha1)

    # --------------------------------------------------------
    # Reduced latitude U1
    # --------------------------------------------------------

    tan_u1 = (
        (1.0 - f)
        * math.tan(phi1)
    )

    cos_u1 = 1.0 / math.sqrt(
        1.0 + tan_u1 * tan_u1
    )

    sin_u1 = (
        tan_u1
        * cos_u1
    )

    sigma1 = math.atan2(
        tan_u1,
        cos_alpha1,
    )

    sin_alpha = (
        cos_u1
        * sin_alpha1
    )

    cos_sq_alpha = max(
        0.0,
        1.0
        - sin_alpha * sin_alpha,
    )

    # --------------------------------------------------------
    # Ellipsoid correction
    # --------------------------------------------------------

    u_sq = (
        cos_sq_alpha
        * (
            a * a
            - b * b
        )
        / (
            b * b
        )
    )

    coeff_a = (
        1.0
        + (
            u_sq / 16384.0
        )
        * (
            4096.0
            + u_sq
            * (
                -768.0
                + u_sq
                * (
                    320.0
                    - 175.0 * u_sq
                )
            )
        )
    )

    coeff_b = (
        u_sq / 1024.0
    ) * (
        256.0
        + u_sq
        * (
            -128.0
            + u_sq
            * (
                74.0
                - 47.0 * u_sq
            )
        )
    )

    # --------------------------------------------------------
    # Solve sigma iteratively
    # --------------------------------------------------------

    sigma = (
        distance_m
        / (
            b * coeff_a
        )
    )

    converged = False

    for _ in range(
        VINCENTY_MAX_ITERATIONS
    ):

        cos_2sigma_m = math.cos(
            2.0 * sigma1
            + sigma
        )

        sin_sigma = math.sin(
            sigma
        )

        cos_sigma = math.cos(
            sigma
        )

        delta_sigma = (
            coeff_b
            * sin_sigma
            * (
                cos_2sigma_m
                + (
                    coeff_b / 4.0
                )
                * (
                    cos_sigma
                    * (
                        -1.0
                        + 2.0
                        * cos_2sigma_m
                        * cos_2sigma_m
                    )
                    - (
                        coeff_b / 6.0
                    )
                    * cos_2sigma_m
                    * (
                        -3.0
                        + 4.0
                        * sin_sigma
                        * sin_sigma
                    )
                    * (
                        -3.0
                        + 4.0
                        * cos_2sigma_m
                        * cos_2sigma_m
                    )
                )
            )
        )

        sigma_next = (
            distance_m
            / (
                b * coeff_a
            )
            + delta_sigma
        )

        if abs(
            sigma_next - sigma
        ) <= VINCENTY_TOLERANCE_RAD:

            sigma = sigma_next
            converged = True
            break

        sigma = sigma_next

    if not converged:
        raise RuntimeError(
            "Vincenty direct solution "
            "did not converge"
        )

    # --------------------------------------------------------
    # Destination latitude
    # --------------------------------------------------------

    sin_sigma = math.sin(
        sigma
    )

    cos_sigma = math.cos(
        sigma
    )

    cos_2sigma_m = math.cos(
        2.0 * sigma1
        + sigma
    )

    tmp = (
        sin_u1
        * sin_sigma
        - cos_u1
        * cos_sigma
        * cos_alpha1
    )

    phi2 = math.atan2(
        (
            sin_u1
            * cos_sigma
            + cos_u1
            * sin_sigma
            * cos_alpha1
        ),
        (
            (1.0 - f)
            * math.sqrt(
                sin_alpha
                * sin_alpha
                + tmp
                * tmp
            )
        ),
    )

    # --------------------------------------------------------
    # Destination longitude
    # --------------------------------------------------------

    lambda_delta = math.atan2(
        (
            sin_sigma
            * sin_alpha1
        ),
        (
            cos_u1
            * cos_sigma
            - sin_u1
            * sin_sigma
            * cos_alpha1
        ),
    )

    c = (
        f
        / 16.0
        * cos_sq_alpha
        * (
            4.0
            + f
            * (
                4.0
                - 3.0
                * cos_sq_alpha
            )
        )
    )

    big_l = (
        lambda_delta
        - (
            1.0 - c
        )
        * f
        * sin_alpha
        * (
            sigma
            + c
            * sin_sigma
            * (
                cos_2sigma_m
                + c
                * cos_sigma
                * (
                    -1.0
                    + 2.0
                    * cos_2sigma_m
                    * cos_2sigma_m
                )
            )
        )
    )

    lambda2 = (
        lambda1
        + big_l
    )

    lat2 = math.degrees(
        phi2
    )

    lon2 = normalize_longitude(
        math.degrees(lambda2)
    )

    return (
        lat2,
        lon2,
    )


def bearing_to_compass(
    bearing_deg: float,
) -> str:

    labels = [
        "N",
        "NE",
        "E",
        "SE",
        "S",
        "SW",
        "W",
        "NW",
    ]

    return labels[
        int(
            (
                normalize_bearing(
                    bearing_deg
                )
                + 22.5
            )
            // 45.0
        )
        % 8
    ]