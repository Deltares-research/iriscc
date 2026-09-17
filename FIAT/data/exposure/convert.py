"""Has been copied from the hydromt-fiat 0.x version."""

from pathlib import Path

import pandas as pd

default_jrc_max_damage_adjustment_values = {
    "construction_cost_vs_depreciated_value_res": 0.6,
    "construction_cost_vs_depreciated_value_com": 0.6,
    "construction_cost_vs_depreciated_value_ind": 0.6,
    "construction_cost_vs_depreciated_value_unk": 0.6,    
    "max_damage_content_inventory_res": 0.5,
    "max_damage_content_inventory_com": 1,
    "max_damage_content_inventory_ind": 1.5,
    "max_damage_content_inventory_unk": 0.9,
    "undamageable_part_res": 0.4,
    "undamageable_part_com": 0.4,
    "undamageable_part_ind": 0.4,
    "undamageable_part_unk": 0.4,
    "material_used_res": 1,
    "material_used_com": 1,
    "material_used_ind": 1,
    "material_used_unk": 1,
}


def preprocess_jrc_damage_values(
    jrc_base_damage_values: pd.DataFrame,
    max_damage_adjustment_values: dict = default_jrc_max_damage_adjustment_values,
) -> pd.DataFrame:
    """Preprocess the JRC damage values data.

    Parameters
    ----------
    jrc_base_damage_values : pd.DataFrame
        The JRC damage values data.
    country : str
        The country to filter the data on.
    eur_to_us_dollar: bool
        Convert JRC Damage Values (Euro 2010) into US-Dollars (2025)

    Returns
    -------
    pd.DataFrame
        The preprocessed JRC damage values data.
    """
    # Create an empty dictionary that will be used to store the damage values per
    # category
    out_dict = {
        "country": jrc_base_damage_values["country"].values,
    }

    # Filter the data on the country
    # jrc_base_damage_values["Country"] = jrc_base_damage_values["Country"].str.lower()
    # jrc_base_damage_values = jrc_base_damage_values.loc[
    #     jrc_base_damage_values["Country"] == country.lower()
    # ]

    # We adjust the max damage values for the different building types with the given
    # or default values
    for building_type in ["residential", "commercial", "industrial", "unknown"]:
        # Get the adjustment values for the building type
        building_type_short = building_type[:3]
        cc_vs_dv = max_damage_adjustment_values[
            f"construction_cost_vs_depreciated_value_{building_type_short}"
        ]
        mdci = max_damage_adjustment_values[
            f"max_damage_content_inventory_{building_type_short}"
        ]
        up = max_damage_adjustment_values[f"undamageable_part_{building_type_short}"]
        mu = max_damage_adjustment_values[f"material_used_{building_type_short}"]

        # Get the JRC base value for the building type
        jrc_base_value = jrc_base_damage_values[building_type].values

        # Calculate the adjusted damage value for structure, content and total damage
        out_dict.update(
            {
                f"{building_type}_structure": (jrc_base_value * cc_vs_dv * (1 - up) * mu),
                f"{building_type}_content": ((jrc_base_value * cc_vs_dv * (1 - up) * mu) * mdci),
                building_type: (
                    (jrc_base_value * cc_vs_dv * (1 - up) * mu)
                    + ((jrc_base_value * cc_vs_dv * (1 - up) * mu) * mdci)
                ),
            },
        )

    # Update with the gdp
    out_dict.update({"gdp": jrc_base_damage_values["gdp"].values})

    out_df = pd.DataFrame(out_dict)
    # return the dataframe
    return out_df


if __name__ == "__main__":
    here = Path(__file__).parent
    raw_data = pd.read_csv(Path(here, "jrc_damage_values_raw.csv"))
    df = preprocess_jrc_damage_values(
        raw_data,
    )
    df.to_csv(Path(here, "jrc_damage_values.csv"), index=False)
    pass