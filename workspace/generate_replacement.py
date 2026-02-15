#!/usr/bin/env python3
"""
Generate replacement-text.json for Urban Farming Strategy presentation.

Reads text-inventory.json and produces replacement-text.json,
preserving all paragraph formatting properties but replacing text values
to match the new topic: Urban Farming Strategy - Greenfield AgriCo.
"""

import json
import copy
from pathlib import Path

WORKSPACE = Path(__file__).parent
INVENTORY_PATH = WORKSPACE / "text-inventory.json"
OUTPUT_PATH = WORKSPACE / "replacement-text.json"


def _p(text: str, **overrides) -> dict:
    """Build a paragraph dict from text + optional formatting overrides."""
    para = {"text": text}
    para.update(overrides)
    return para


def copy_format(original: dict, new_text: str) -> dict:
    """Copy all formatting keys from *original* paragraph, replacing only text."""
    para = copy.deepcopy(original)
    para["text"] = new_text
    return para


def build_replacement(inventory: dict) -> dict:
    """Return the full replacement dict, slide-by-slide."""

    rep = {}

    # ── slide-0: Title ──────────────────────────────────────────────────
    rep["slide-0"] = {
        "shape-0": {"paragraphs": [_p("March 2025")]},
        "shape-1": {"paragraphs": [
            copy_format(inventory["slide-0"]["shape-1"]["paragraphs"][0],
                        "Urban Farming Strategy")
        ]},
        "shape-2": {"paragraphs": [
            copy_format(inventory["slide-0"]["shape-2"]["paragraphs"][0],
                        "Greenfield AgriCo market entry and case for change in Southeast Asia")
        ]},
    }

    # ── slide-1: Contacts ───────────────────────────────────────────────
    orig1 = inventory["slide-1"]

    contacts = [
        # (shape, name, role, location_email)
        ("shape-1", "Sarah Chen", "Engagement Partner",
         "Singapore\x0bsarah.chen\x0b@strategyand.sg.pwc.com"),
        ("shape-2", "Marcus Rivera", "Subject Matter Expert",
         "Australia\x0bmarcus.rivera\x0b@strategyand.au.pwc.com"),
        ("shape-3", "Priya Sharma", "Engagement Director",
         "Singapore\x0bpriya.sharma\x0b@strategyand.sg.pwc.com"),
        ("shape-4", "James Wong", "Client Relationship Manager",
         "Singapore\x0bjames.wong\x0b@sg.pwc.com"),
        ("shape-5", "Rachel Lim", "Engagement Manager", None),
        ("shape-6", "David Tan", "Work Stream Lead",
         "Malaysia\x0bdavid.tan\x0b@strategyand.my.pwc.com"),
        ("shape-7", "Lisa Ng", "Work Stream Lead", None),
        ("shape-8", "Amir Hassan", "Work Stream Lead",
         "Malaysia\x0bamir.hassan\x0b@strategyand.my.pwc.com"),
        ("shape-9", "Kevin Park", "Analyst",
         "Singapore\x0bkevin.park\x0b@strategyand.sg.pwc.com"),
        ("shape-10", "Emma Lee", "Analyst", None),
    ]

    s1 = {}
    # shape-0 title
    s1["shape-0"] = {"paragraphs": [
        _p("For questions related to this document please contact any one of our team members")
    ]}

    for shape_id, name, role, loc_email in contacts:
        orig_paras = orig1[shape_id]["paragraphs"]
        paras = []
        # paragraph 0 – name (bold)
        paras.append(copy_format(orig_paras[0], name))
        # paragraph 1 – role
        paras.append(copy_format(orig_paras[1], role))

        if shape_id == "shape-5":
            # Original has 4 paragraphs: name, role, location, email
            paras.append(copy_format(orig_paras[2], "Singapore"))
            paras.append(copy_format(orig_paras[3],
                                     "rachel.lim\x0b@strategyand.sg.pwc.com"))
        elif shape_id == "shape-7":
            # Original has 5 paragraphs: name, role, location, email-user, email-domain
            paras.append(copy_format(orig_paras[2], "Singapore"))
            paras.append(copy_format(orig_paras[3], "lisa.ng"))
            paras.append(copy_format(orig_paras[4], "@strategyand.sg.pwc.com"))
        elif shape_id == "shape-10":
            # Original has 4 paragraphs: name, role, location+email-user, email-domain
            paras.append(copy_format(orig_paras[2], "Singapore\x0bemma.lee"))
            paras.append(copy_format(orig_paras[3], "@strategyand.sg.pwc.com"))
        else:
            # 3-paragraph contacts
            paras.append(copy_format(orig_paras[2], loc_email))

        s1[shape_id] = {"paragraphs": paras}

    # shape-11 footer
    s1["shape-11"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}

    rep["slide-1"] = s1

    # ── slide-2: Project Qualification ──────────────────────────────────
    rep["slide-2"] = {
        "shape-0": {"paragraphs": [
            _p("Project Qualification: \x0bUrban Farming Strategy for an AgriCo in South East Asia")
        ]},
        "shape-1": {"paragraphs": [
            _p("Confidential information for the sole benefit and use of PwC's client.")
        ]},
    }

    # ── slide-3: Smart Food Security ────────────────────────────────────
    o3 = inventory["slide-3"]
    rep["slide-3"] = {
        "shape-0": {"paragraphs": [
            _p("In support of country's Smart Food Security agenda, client aims to establish an AgriCo to further drive urban farming adoption")
        ]},
        "shape-1": {"paragraphs": [
            copy_format(o3["shape-1"]["paragraphs"][0],
                        "Country Food Security Target")
        ]},
        "shape-2": {"paragraphs": [
            copy_format(o3["shape-2"]["paragraphs"][0],
                        "Clients Objectives")
        ]},
        "shape-3": {"paragraphs": [
            copy_format(o3["shape-3"]["paragraphs"][0],
                        "Develop a national urban farming solution through AgriCo that aims to:"),
            copy_format(o3["shape-3"]["paragraphs"][1],
                        "Promote vertical farming for retail and restaurant supply chains"),
            copy_format(o3["shape-3"]["paragraphs"][2],
                        "Support food banks and the social sector"),
            copy_format(o3["shape-3"]["paragraphs"][3],
                        "Establish a forward-looking view (including emerging and key trends) of the agriculture landscape"),
            copy_format(o3["shape-3"]["paragraphs"][4],
                        "Determine the ways-to-play (incl. op model, target markets) for AgriCo to accelerate adoption of local produce"),
            copy_format(o3["shape-3"]["paragraphs"][5],
                        "Design infrastructure that is future ready by exploring all relevant current and potential technologies – assess suitability of existing national farming infrastructure"),
            copy_format(o3["shape-3"]["paragraphs"][6],
                        "Explore opportunities to leverage on existing investments for the collaboration"),
        ]},
        "shape-4": {"paragraphs": [
            copy_format(o3["shape-4"]["paragraphs"][0],
                        "Interoperable farming system"),
            copy_format(o3["shape-4"]["paragraphs"][1],
                        "Simple distribution network"),
            copy_format(o3["shape-4"]["paragraphs"][2],
                        "Faster harvest cycles"),
            copy_format(o3["shape-4"]["paragraphs"][3],
                        "Safer produce standards"),
        ]},
        "shape-5": {"paragraphs": [
            copy_format(o3["shape-5"]["paragraphs"][0],
                        "Higher accessibility and acceptance for consumers and businesses")
        ]},
        "shape-6": {"paragraphs": [
            copy_format(o3["shape-6"]["paragraphs"][0],
                        "A simplified distribution system to increase competitiveness and efficiency for users")
        ]},
        "shape-7": {"paragraphs": [
            _p("Confidential information for the sole benefit and use of PwC's client.")
        ]},
        "shape-8": {"paragraphs": [
            copy_format(o3["shape-8"]["paragraphs"][0],
                        "Increased speed of harvest-to-table via controlled environment agriculture")
        ]},
        "shape-9": {"paragraphs": [
            copy_format(o3["shape-9"]["paragraphs"][0],
                        "A fully regulated food safety environment (e.g. establishment of the Food Standards Council)")
        ]},
    }

    # ── slide-4: Disruptors / Farming models ────────────────────────────
    o4 = inventory["slide-4"]
    s4 = {}
    s4["shape-0"] = {"paragraphs": [
        _p("In response to top-down call to action, disruptors are entering the market with two variations of urban farming propositions")
    ]}
    s4["shape-1"] = {"paragraphs": [
        copy_format(o4["shape-1"]["paragraphs"][0],
                    "Farming models available")
    ]}
    s4["shape-2"] = {"paragraphs": [
        copy_format(o4["shape-2"]["paragraphs"][0],
                    "Indoor Vertical Farms")
    ]}
    s4["shape-3"] = {"paragraphs": [
        copy_format(o4["shape-3"]["paragraphs"][0],
                    "Rooftop Greenhouses")
    ]}
    s4["shape-4"] = {"paragraphs": [
        copy_format(o4["shape-4"]["paragraphs"][0],
                    "Community Gardens (or more)")
    ]}
    s4["shape-5"] = {"paragraphs": [
        copy_format(o4["shape-5"]["paragraphs"][0],
                    "Produce grown and distributed directly by operator to consumer")
    ]}
    s4["shape-6"] = {"paragraphs": [
        copy_format(o4["shape-6"]["paragraphs"][0],
                    "Operators grow and distribute produce. Distribution is dependent on a specific network and delivery arrangement")
    ]}
    s4["shape-7"] = {"paragraphs": [
        copy_format(o4["shape-7"]["paragraphs"][0],
                    "Operators only grow produce. Distribution is broadly accepted via existing wholesale and retail supply chains")
    ]}
    s4["shape-8"] = {"paragraphs": [
        copy_format(o4["shape-8"]["paragraphs"][0], "Operators:")
    ]}
    s4["shape-9"] = {"paragraphs": [
        copy_format(o4["shape-9"]["paragraphs"][0], "Operators:")
    ]}
    s4["shape-10"] = {"paragraphs": [
        copy_format(o4["shape-10"]["paragraphs"][0], "Operators:")
    ]}
    s4["shape-11"] = {"paragraphs": [
        copy_format(o4["shape-11"]["paragraphs"][0],
                    "Recently opened to third party growers")
    ]}
    s4["shape-12"] = {"paragraphs": [
        copy_format(o4["shape-12"]["paragraphs"][0], "Closed-loop farms"),
        copy_format(o4["shape-12"]["paragraphs"][1], "(Controlled env.)"),
    ]}
    s4["shape-13"] = {"paragraphs": [
        copy_format(o4["shape-13"]["paragraphs"][0], "1")
    ]}
    s4["shape-14"] = {"paragraphs": [
        copy_format(o4["shape-14"]["paragraphs"][0], "2")
    ]}
    s4["shape-15"] = {"paragraphs": [
        copy_format(o4["shape-15"]["paragraphs"][0],
                    "Open-network farms\x0b(Multi-crop platform)")
    ]}
    s4["shape-16"] = {"paragraphs": [
        copy_format(o4["shape-16"]["paragraphs"][0],
                    "Source: AgriTech Asia, PwC Strategy& analysis")
    ]}
    s4["shape-17"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s4["shape-18"] = {"paragraphs": [
        copy_format(o4["shape-18"]["paragraphs"][0], "Grower/Distributor")
    ]}
    s4["shape-19"] = {"paragraphs": [
        copy_format(o4["shape-19"]["paragraphs"][0], "Grower")
    ]}
    s4["shape-20"] = {"paragraphs": [
        copy_format(o4["shape-20"]["paragraphs"][0], "Distributor")
    ]}
    s4["shape-21"] = {"paragraphs": [
        copy_format(o4["shape-21"]["paragraphs"][0], "Consumer")
    ]}
    s4["shape-22"] = {"paragraphs": [
        copy_format(o4["shape-22"]["paragraphs"][0], "Merchant")
    ]}
    s4["shape-23"] = {"paragraphs": [
        copy_format(o4["shape-23"]["paragraphs"][0], "Merchant")
    ]}
    s4["shape-24"] = {"paragraphs": [
        copy_format(o4["shape-24"]["paragraphs"][0], "Merchant")
    ]}
    s4["shape-25"] = {"paragraphs": [
        copy_format(o4["shape-25"]["paragraphs"][0], "Consumer")
    ]}
    s4["shape-26"] = {"paragraphs": [
        copy_format(o4["shape-26"]["paragraphs"][0], "Consumer")
    ]}
    rep["slide-4"] = s4

    # ── slide-5: Competitor landscape ───────────────────────────────────
    o5 = inventory["slide-5"]
    rep["slide-5"] = {
        "shape-0": {"paragraphs": [
            _p("While disruptors bring choice for consumers, 'Imported Produce' remains the leading option for affordable food")
        ]},
        "shape-1": {"paragraphs": [
            copy_format(o5["shape-1"]["paragraphs"][0],
                        "Competitor Landscape Analysis")
        ]},
        "shape-2": {"paragraphs": [
            copy_format(o5["shape-2"]["paragraphs"][0],
                        "Operators were assessed across seven lenses \u2013 produce variety, freshness, interoperability, harvest speed, cost to merchants, customer reach, and food safety")
        ]},
        "shape-3": {"paragraphs": [
            copy_format(o5["shape-3"]["paragraphs"][0],
                        "The urban farming operators selected for assessment were filtered based on their significance in the market")
        ]},
        "shape-4": {"paragraphs": [
            _p("Confidential information for the sole benefit and use of PwC's client.")
        ]},
    }

    # ── slide-6: Non-differentiating efforts ────────────────────────────
    o6 = inventory["slide-6"]
    s6 = {}
    s6["shape-0"] = {"paragraphs": [
        _p("Non-differentiating efforts by players often reap marginal benefits as consumer pain points remain unaddressed")
    ]}
    s6["shape-1"] = {"paragraphs": [
        copy_format(o6["shape-1"]["paragraphs"][0],
                    "Differentiating efforts of players")
    ]}
    s6["shape-2"] = {"paragraphs": [
        copy_format(o6["shape-2"]["paragraphs"][0],
                    "Tech-led vertical farms")
    ]}
    s6["shape-3"] = {"paragraphs": [
        copy_format(o6["shape-3"]["paragraphs"][0],
                    "Technology-driven farming solutions available (app-based) to consumers upon subscription. The platform allows for B2C and B2B produce ordering")
    ]}
    s6["shape-4"] = {"paragraphs": [
        copy_format(o6["shape-4"]["paragraphs"][0], "Description")
    ]}
    s6["shape-5"] = {"paragraphs": [
        copy_format(o6["shape-5"]["paragraphs"][0], "Key takeaway")
    ]}
    s6["shape-6"] = {"paragraphs": [
        copy_format(o6["shape-6"]["paragraphs"][0],
                    "Retailer co-branded farms")
    ]}
    s6["shape-7"] = {"paragraphs": [
        copy_format(o6["shape-7"]["paragraphs"][0],
                    "Co-branded farms are collaborative efforts by a retailer and a farm operator to provide fresh produce directly in-store, usually aimed to drive shared customer loyalty")
    ]}
    s6["shape-8"] = {"paragraphs": [
        copy_format(o6["shape-8"]["paragraphs"][0],
                    "Consumer experience is compromised as operators try to diversify and differentiate themselves"),
        copy_format(o6["shape-8"]["paragraphs"][1],
                    "Consumers often have to travel to specific locations or wait for delivery windows (inconvenient)"),
        copy_format(o6["shape-8"]["paragraphs"][2],
                    "Interoperability is still lacking as produce offerings are limited to specific operator networks and restricted to pre-approved merchants"),
        copy_format(o6["shape-8"]["paragraphs"][3],
                    "Lack of quality standards and traceability measures result in spoilage and waste \u2013 business model becomes unsustainable"),
    ]}
    s6["shape-9"] = {"paragraphs": [
        copy_format(o6["shape-9"]["paragraphs"][0],
                    "Disruptive farm-to-table play")
    ]}
    s6["shape-10"] = {"paragraphs": [
        copy_format(o6["shape-10"]["paragraphs"][0],
                    "Disruptors enter the farming landscape with intentions to maximise direct-to-consumer freshness to support core business. Discounts and incentives are offered frequently to consumers")
    ]}
    s6["shape-11"] = {"paragraphs": [
        copy_format(o6["shape-11"]["paragraphs"][0],
                    "Subscription harvest services")
    ]}
    s6["shape-12"] = {"paragraphs": [
        copy_format(o6["shape-12"]["paragraphs"][0],
                    "Operators are providing a subscription harvest service that allows consumers to pre-order seasonal produce and receive regular deliveries, assisting consumers with fresh food access")
    ]}
    s6["shape-13"] = {"paragraphs": [
        copy_format(o6["shape-13"]["paragraphs"][0],
                    "Reduction in costs to consumers")
    ]}
    s6["shape-14"] = {"paragraphs": [
        copy_format(o6["shape-14"]["paragraphs"][0], "SkyGreens")
    ]}
    s6["shape-15"] = {"paragraphs": [
        copy_format(o6["shape-15"]["paragraphs"][0],
                    "Operators are expected to reduce distribution margins in order to remain competitive and encourage merchant adoption (e.g. SkyGreens have reduced margins for some merchants to 5% per kg from 20%)")
    ]}
    s6["shape-16"] = {"paragraphs": [
        copy_format(o6["shape-16"]["paragraphs"][0],
                    "Source: Company websites, Straits Times, PwC Strategy& analysis")
    ]}
    s6["shape-17"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s6["shape-18"] = {"paragraphs": [
        copy_format(o6["shape-18"]["paragraphs"][0], "Sustenir Agri")
    ]}
    rep["slide-6"] = s6

    # ── slide-7: Household perspective ──────────────────────────────────
    o7 = inventory["slide-7"]
    s7 = {}
    s7["shape-0"] = {"paragraphs": [
        _p("The country's grassroots still prefer imported produce especially for daily meals \u2013 a habit entrenched in hearts and minds")
    ]}
    s7["shape-1"] = {"paragraphs": [
        copy_format(o7["shape-1"]["paragraphs"][0],
                    "Dominant Sourcing Mode: A Household's Perspective")
    ]}
    s7["shape-2"] = {"paragraphs": [
        copy_format(o7["shape-2"]["paragraphs"][0],
                    "Imported produce is a norm in every household as it is affordable, available, familiar, and widely stocked")
    ]}
    s7["shape-3"] = {"paragraphs": [
        copy_format(o7["shape-3"]["paragraphs"][0], "Yeo Soo Keng, 78")
    ]}
    s7["shape-4"] = {"paragraphs": [
        copy_format(o7["shape-4"]["paragraphs"][0], "Maria, 35")
    ]}
    s7["shape-5"] = {"paragraphs": [
        copy_format(o7["shape-5"]["paragraphs"][0], "Pioneer (>65 years)")
    ]}
    s7["shape-6"] = {"paragraphs": [
        copy_format(o7["shape-6"]["paragraphs"][0],
                    "Buys groceries for daily meals \u2013 wet market, supermarket, hawker centres"),
        copy_format(o7["shape-6"]["paragraphs"][1],
                    "Buys only imported produce due to familiarity and lower price"),
    ]}
    s7["shape-7"] = {"paragraphs": [
        copy_format(o7["shape-7"]["paragraphs"][0], "Tan Chun Kit, 58")
    ]}
    s7["shape-8"] = {"paragraphs": [
        copy_format(o7["shape-8"]["paragraphs"][0], "Goh King Kuan, 50")
    ]}
    s7["shape-9"] = {"paragraphs": [
        copy_format(o7["shape-9"]["paragraphs"][0],
                    "Foreign Worker (20 \u2013 44 years)")
    ]}
    s7["shape-10"] = {"paragraphs": [
        copy_format(o7["shape-10"]["paragraphs"][0],
                    "Buys only when requested by employer, mostly household groceries"),
        copy_format(o7["shape-10"]["paragraphs"][1],
                    "Buys imported produce as it is the usual option provided by the employer"),
        copy_format(o7["shape-10"]["paragraphs"][2],
                    "Receives food allowance and sends savings home to family physically"),
    ]}
    s7["shape-11"] = {"paragraphs": [
        copy_format(o7["shape-11"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s7["shape-12"] = {"paragraphs": [
        copy_format(o7["shape-12"]["paragraphs"][0], "Daniel Tan, 26")
    ]}
    s7["shape-13"] = {"paragraphs": [
        copy_format(o7["shape-13"]["paragraphs"][0], "Marc Tan, 18")
    ]}
    s7["shape-14"] = {"paragraphs": [
        copy_format(o7["shape-14"]["paragraphs"][0], "Becky Tan, 12")
    ]}
    s7["shape-15"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s7["shape-16"] = {"paragraphs": [
        copy_format(o7["shape-16"]["paragraphs"][0],
                    "Silver Hair (45 \u2013 65 years)")
    ]}
    s7["shape-17"] = {"paragraphs": [
        copy_format(o7["shape-17"]["paragraphs"][0],
                    "Provides for family, buys groceries and meals from markets"),
        copy_format(o7["shape-17"]["paragraphs"][1],
                    "Buys imported produce or visits supermarket chains"),
        copy_format(o7["shape-17"]["paragraphs"][2],
                    "Prefers imported produce for daily cooking needs"),
    ]}
    s7["shape-18"] = {"paragraphs": [
        copy_format(o7["shape-18"]["paragraphs"][0],
                    "Teen and Young (<19 years)")
    ]}
    s7["shape-19"] = {"paragraphs": [
        copy_format(o7["shape-19"]["paragraphs"][0],
                    "Eats meals prepared by parents using mostly imported ingredients"),
        copy_format(o7["shape-19"]["paragraphs"][1],
                    "Buys snacks and meals using pocket money at hawker centres and convenience stores"),
    ]}
    s7["shape-20"] = {"paragraphs": [
        copy_format(o7["shape-20"]["paragraphs"][0],
                    "Young Adult (20 \u2013 44 years)")
    ]}
    s7["shape-21"] = {"paragraphs": [
        copy_format(o7["shape-21"]["paragraphs"][0],
                    "Buys groceries for meals, dining out, and retail food shopping"),
        copy_format(o7["shape-21"]["paragraphs"][1],
                    "Buys imported produce, occasionally tries local organic options"),
        copy_format(o7["shape-21"]["paragraphs"][2],
                    "Open to local produce, prefers imported for affordability"),
    ]}
    rep["slide-7"] = s7

    # ── slide-8: Hawker / small merchant perspective ────────────────────
    o8 = inventory["slide-8"]
    s8 = {}
    s8["shape-0"] = {"paragraphs": [
        _p("From a small merchant perspective, hawkers prefer imported ingredients due to their affordability and wide availability")
    ]}
    s8["shape-1"] = {"paragraphs": [
        copy_format(o8["shape-1"]["paragraphs"][0],
                    "Day-in-life of a Hawker \u2013 Overview")
    ]}
    s8["shape-2"] = {"paragraphs": [
        copy_format(o8["shape-2"]["paragraphs"][0], "Suppliers:"),
        copy_format(o8["shape-2"]["paragraphs"][1],
                    "Chun Kit has to go to the wet market early morning to source his ingredients for the day's cooking"),
        copy_format(o8["shape-2"]["paragraphs"][2],
                    "His suppliers stock mainly imported produce as it is cheaper and more readily available"),
    ]}
    s8["shape-3"] = {"paragraphs": [
        copy_format(o8["shape-3"]["paragraphs"][0], "Needs:")
    ]}
    s8["shape-4"] = {"paragraphs": [
        copy_format(o8["shape-4"]["paragraphs"][0], "Operations:"),
        copy_format(o8["shape-4"]["paragraphs"][1],
                    "Chun Kit's busiest hours are between 12pm to 2pm. He serves ~90 bowls of fish soup during that period at ~$4 each"),
        copy_format(o8["shape-4"]["paragraphs"][2],
                    "A small % of customers asks about locally-farmed ingredients but are satisfied with the taste of imported produce"),
    ]}
    s8["shape-5"] = {"paragraphs": [
        copy_format(o8["shape-5"]["paragraphs"][0],
                    "Import Supply Cycle")
    ]}
    s8["shape-6"] = {"paragraphs": [
        copy_format(o8["shape-6"]["paragraphs"][0], "Affordability")
    ]}
    s8["shape-7"] = {"paragraphs": [
        copy_format(o8["shape-7"]["paragraphs"][0], "Availability")
    ]}
    s8["shape-8"] = {"paragraphs": [
        copy_format(o8["shape-8"]["paragraphs"][0], "Reliability of Supply")
    ]}
    s8["shape-9"] = {"paragraphs": [
        copy_format(o8["shape-9"]["paragraphs"][0],
                    "Tan Chun Kit, 58 years old, is a hawker selling fish soup. He employs 1 stall assistant and operates between 7.30am \u2013 4.30pm. Imported ingredients are his dominant source of supply."),
        copy_format(o8["shape-9"]["paragraphs"][1],
                    "Chun Kit is the primary breadwinner of his family, which consists of his wife and 2 sons who are still in school. He currently lives in a 3-room flat."),
    ]}
    s8["shape-10"] = {"paragraphs": [
        copy_format(o8["shape-10"]["paragraphs"][0], "Tan Chun Kit, 58")
    ]}
    s8["shape-11"] = {"paragraphs": [
        copy_format(o8["shape-11"]["paragraphs"][0], "Family:"),
        copy_format(o8["shape-11"]["paragraphs"][1],
                    "After Chun Kit closes his stall for the day, he goes to a nearby food centre to pack food for his family \u2013 imported produce is the main ingredient used in the food centre"),
        copy_format(o8["shape-11"]["paragraphs"][2],
                    "Chun Kit's sons ask him for dinner money after school for a meal at the hawker centre \u2013 imported ingredients are the most affordable and convenient option for hawkers"),
    ]}
    s8["shape-12"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s8["shape-13"] = {"paragraphs": [
        copy_format(o8["shape-13"]["paragraphs"][0], "Morning")
    ]}
    s8["shape-14"] = {"paragraphs": [
        copy_format(o8["shape-14"]["paragraphs"][0], "Mid-day")
    ]}
    s8["shape-15"] = {"paragraphs": [
        copy_format(o8["shape-15"]["paragraphs"][0], "Evening")
    ]}
    rep["slide-8"] = s8

    # ── slide-9: Cost comparison ────────────────────────────────────────
    o9 = inventory["slide-9"]
    s9 = {}
    s9["shape-0"] = {"paragraphs": [
        copy_format(o9["shape-0"]["paragraphs"][0],
                    "Example: Imported and locally-farmed produce are about cost neutral to hawkers \u2013 no compelling incentive to adopt local farming")
    ]}
    s9["shape-1"] = {"paragraphs": [
        copy_format(o9["shape-1"]["paragraphs"][0],
                    "Case Study: Cost of Imported vs. Locally-Farmed Produce")
    ]}
    s9["shape-2"] = {"paragraphs": [
        copy_format(o9["shape-2"]["paragraphs"][0],
                    "Scenario 1: Imported Only")
    ]}
    s9["shape-3"] = {"paragraphs": [
        copy_format(o9["shape-3"]["paragraphs"][0], "1 hour")
    ]}
    s9["shape-4"] = {"paragraphs": [
        copy_format(o9["shape-4"]["paragraphs"][0],
                    "Cost of Import Sourcing")
    ]}
    s9["shape-5"] = {"paragraphs": [
        copy_format(o9["shape-5"]["paragraphs"][0], "ILLUSTRATIVE")
    ]}
    s9["shape-6"] = {"paragraphs": [
        copy_format(o9["shape-6"]["paragraphs"][0], "Sourcing")
    ]}
    s9["shape-7"] = {"paragraphs": [
        copy_format(o9["shape-7"]["paragraphs"][0],
                    "Chun Kit only sources imported ingredients \u2013 spending $80 per day on produce for 140 bowls of fish soup")
    ]}
    s9["shape-8"] = {"paragraphs": [
        copy_format(o9["shape-8"]["paragraphs"][0], "Quality Check")
    ]}
    s9["shape-9"] = {"paragraphs": [
        copy_format(o9["shape-9"]["paragraphs"][0],
                    "End of day, Chun Kit inspects the remaining stock, estimating wastage against the day's usage")
    ]}
    s9["shape-10"] = {"paragraphs": [
        copy_format(o9["shape-10"]["paragraphs"][0], "Market Trip")
    ]}
    s9["shape-11"] = {"paragraphs": [
        copy_format(o9["shape-11"]["paragraphs"][0],
                    "Chun Kit travels to the wet market to restock imported ingredients for the next day, spending 1 hour for quality check and restocking")
    ]}
    s9["shape-12"] = {"paragraphs": [
        copy_format(o9["shape-12"]["paragraphs"][0],
                    "1 hour per day of quality check and market trip"),
        copy_format(o9["shape-12"]["paragraphs"][1],
                    "$10 per hour opportunity cost to Chun Kit1"),
        copy_format(o9["shape-12"]["paragraphs"][2],
                    "365 days of operation per year"),
    ]}
    s9["shape-13"] = {"paragraphs": [
        copy_format(o9["shape-13"]["paragraphs"][0],
                    "Opportunity cost per annum: $3,650")
    ]}
    s9["shape-14"] = {"paragraphs": [
        copy_format(o9["shape-14"]["paragraphs"][0],
                    "Avg. impact to profitability4: ~5%")
    ]}
    s9["shape-15"] = {"paragraphs": [
        copy_format(o9["shape-15"]["paragraphs"][0],
                    "Scenario 2: Locally-Farmed Only")
    ]}
    s9["shape-16"] = {"paragraphs": [
        copy_format(o9["shape-16"]["paragraphs"][0], "Sourcing")
    ]}
    s9["shape-17"] = {"paragraphs": [
        copy_format(o9["shape-17"]["paragraphs"][0], "Quality Check")
    ]}
    s9["shape-18"] = {"paragraphs": [
        copy_format(o9["shape-18"]["paragraphs"][0], "20 mins")
    ]}
    s9["shape-19"] = {"paragraphs": [
        copy_format(o9["shape-19"]["paragraphs"][0], "Home")
    ]}
    s9["shape-20"] = {"paragraphs": [
        copy_format(o9["shape-20"]["paragraphs"][0],
                    "Cost of Local Produce")
    ]}
    s9["shape-21"] = {"paragraphs": [
        copy_format(o9["shape-21"]["paragraphs"][0],
                    "~$200,000 revenue per year2"),
        copy_format(o9["shape-21"]["paragraphs"][1],
                    "5% \u2013 15% premium per kg for local produce3"),
        copy_format(o9["shape-21"]["paragraphs"][2],
                    "20 mins per day at $10 per hour1"),
    ]}
    s9["shape-22"] = {"paragraphs": [
        copy_format(o9["shape-22"]["paragraphs"][0],
                    "Chun Kit sources locally-farmed ingredients for all 140 bowls of fish soup everyday, incurring 5% - 15% price premium per kg")
    ]}
    s9["shape-23"] = {"paragraphs": [
        copy_format(o9["shape-23"]["paragraphs"][0],
                    "End of day, Chun Kit performs a quick freshness check to ensure produce received matches quality standards")
    ]}
    s9["shape-24"] = {"paragraphs": [
        copy_format(o9["shape-24"]["paragraphs"][0],
                    "Chun Kit goes home and his work is done for the day")
    ]}
    s9["shape-25"] = {"paragraphs": [
        copy_format(o9["shape-25"]["paragraphs"][0],
                    "Avg. annual premium: $4,900")
    ]}
    s9["shape-26"] = {"paragraphs": [
        copy_format(o9["shape-26"]["paragraphs"][0],
                    "Avg. impact to profitability4: ~6%")
    ]}
    s9["shape-27"] = {"paragraphs": [
        copy_format(o9["shape-27"]["paragraphs"][0],
                    "Note: 1) Hourly opportunity cost is based on average per hour wage adjusted for realisable savings amount of $10; 2) ~$200,000 revenue per year is based on $560 revenue per day multiplied by 365 operational days per year; 3) Price premium range is based on competitive rates \u2013 local farms (5%) to certified organic (15%); 4) Profitability is assumed to be 40% of revenue at $80,000 based on average gross margins for hawkers"),
        copy_format(o9["shape-27"]["paragraphs"][1],
                    "Source: AVA; PwC Strategy& analysis"),
    ]}
    s9["shape-28"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    rep["slide-9"] = s9

    # ── slide-10: Breaking the cycle ────────────────────────────────────
    o10 = inventory["slide-10"]
    s10 = {}
    s10["shape-0"] = {"paragraphs": [
        _p("In order to encourage local produce adoption, the import dependency cycle needs to be broken without affecting family needs")
    ]}
    s10["shape-1"] = {"paragraphs": [
        copy_format(o10["shape-1"]["paragraphs"][0],
                    "Current State Supply Cycle \u2013 Import-Based")
    ]}
    s10["shape-2"] = {"paragraphs": [
        copy_format(o10["shape-2"]["paragraphs"][0], "2")
    ]}
    s10["shape-3"] = {"paragraphs": [
        copy_format(o10["shape-3"]["paragraphs"][0], "3")
    ]}
    s10["shape-4"] = {"paragraphs": [
        copy_format(o10["shape-4"]["paragraphs"][0],
                    "Soo Keng receives groceries from Chun Kit and prepares daily meals using imported ingredients \u2013 vegetables, meat, and some household staples")
    ]}
    s10["shape-5"] = {"paragraphs": [
        copy_format(o10["shape-5"]["paragraphs"][0], "Future State")
    ]}
    s10["shape-6"] = {"paragraphs": [
        copy_format(o10["shape-6"]["paragraphs"][0], "1")
    ]}
    s10["shape-7"] = {"paragraphs": [
        copy_format(o10["shape-7"]["paragraphs"][0], "Yeo Soo Keng, 78")
    ]}
    s10["shape-8"] = {"paragraphs": [
        copy_format(o10["shape-8"]["paragraphs"][0],
                    "Local produce adoption can be facilitated by breaking the import cycle simultaneously, increasing overall local food supply"),
        copy_format(o10["shape-8"]["paragraphs"][1],
                    "Chun Kit receives produce directly from the AgriCo network without needing a physical wet market trip"),
        copy_format(o10["shape-8"]["paragraphs"][2],
                    "Produce is distributed directly to Soo Keng, Marc, and Maria via local delivery networks"),
        copy_format(o10["shape-8"]["paragraphs"][3],
                    "As local farming becomes widely adopted, Soo Keng, Marc, and Maria can source fresh produce locally without relying on imports"),
    ]}
    s10["shape-9"] = {"paragraphs": [
        copy_format(o10["shape-9"]["paragraphs"][0], "Tan Chun Kit, 58")
    ]}
    s10["shape-10"] = {"paragraphs": [
        copy_format(o10["shape-10"]["paragraphs"][0],
                    "Marc receives meal money from Chun Kit and eats at hawker centres using imported ingredients \u2013 meals, snacks, entertainment")
    ]}
    s10["shape-11"] = {"paragraphs": [
        copy_format(o10["shape-11"]["paragraphs"][0], "1")
    ]}
    s10["shape-12"] = {"paragraphs": [
        copy_format(o10["shape-12"]["paragraphs"][0],
                    "Chun Kit sources ingredients through the wet market supply chain. He proceeds to the market early morning to:"),
        copy_format(o10["shape-12"]["paragraphs"][1],
                    "Buy groceries for his mother, Soo Keng, and son, Marc"),
        copy_format(o10["shape-12"]["paragraphs"][2],
                    "Provide food supplies for his household helper, Maria"),
    ]}
    s10["shape-13"] = {"paragraphs": [
        copy_format(o10["shape-13"]["paragraphs"][0], "Marc Tan, 18")
    ]}
    s10["shape-14"] = {"paragraphs": [
        copy_format(o10["shape-14"]["paragraphs"][0], "2")
    ]}
    s10["shape-15"] = {"paragraphs": [
        copy_format(o10["shape-15"]["paragraphs"][0],
                    "Maria receives groceries and proceeds to the nearest convenience store to buy additional household items for the family")
    ]}
    s10["shape-16"] = {"paragraphs": [
        copy_format(o10["shape-16"]["paragraphs"][0], "3")
    ]}
    s10["shape-17"] = {"paragraphs": [
        copy_format(o10["shape-17"]["paragraphs"][0], "Maria, 35")
    ]}
    s10["shape-18"] = {"paragraphs": [
        copy_format(o10["shape-18"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s10["shape-19"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    rep["slide-10"] = s10

    # ── slide-11: Five key needs ────────────────────────────────────────
    o11 = inventory["slide-11"]
    s11 = {}
    s11["shape-0"] = {"paragraphs": [
        _p("There are five key needs of new urban farming offering that will appeal to the People and beyond")
    ]}
    s11["shape-1"] = {"paragraphs": [
        copy_format(o11["shape-1"]["paragraphs"][0], "Produce Category")
    ]}
    s11["shape-2"] = {"paragraphs": [
        copy_format(o11["shape-2"]["paragraphs"][0],
                    "Consumer Facing Produce Example Use Cases")
    ]}
    s11["shape-3"] = {"paragraphs": [
        copy_format(o11["shape-3"]["paragraphs"][0], "Supply Flow")
    ]}
    s11["shape-4"] = {"paragraphs": [
        copy_format(o11["shape-4"]["paragraphs"][0], "Distribution Channel")
    ]}
    s11["shape-5"] = {"paragraphs": [
        copy_format(o11["shape-5"]["paragraphs"][0], "NON-EXHAUSTIVE")
    ]}
    s11["shape-6"] = {"paragraphs": [
        copy_format(o11["shape-6"]["paragraphs"][0],
                    "Fresh produce delivery")
    ]}
    s11["shape-7"] = {"paragraphs": [
        copy_format(o11["shape-7"]["paragraphs"][0],
                    "Delivery via local farms, online platforms, or neighbourhood collection points \u2013 wide range of channels")
    ]}
    s11["shape-8"] = {"paragraphs": [
        copy_format(o11["shape-8"]["paragraphs"][0],
                    "Restaurant supply")
    ]}
    s11["shape-9"] = {"paragraphs": [
        copy_format(o11["shape-9"]["paragraphs"][0], "Sanitised")
    ]}
    s11["shape-10"] = {"paragraphs": [
        copy_format(o11["shape-10"]["paragraphs"][0],
                    "Produce supplied via wholesale \u2013 fragmented and lengthy distribution process")
    ]}
    s11["shape-11"] = {"paragraphs": [
        copy_format(o11["shape-11"]["paragraphs"][0],
                    "School meals")
    ]}
    s11["shape-12"] = {"paragraphs": [
        copy_format(o11["shape-12"]["paragraphs"][0],
                    "Produce sourcing mostly done via importers, emerging offerings with local farms")
    ]}
    s11["shape-13"] = {"paragraphs": [
        copy_format(o11["shape-13"]["paragraphs"][0], "Fresh"),
        copy_format(o11["shape-13"]["paragraphs"][1], "Widely available"),
        copy_format(o11["shape-13"]["paragraphs"][2], "Traceable (e-label)"),
    ]}
    s11["shape-14"] = {"paragraphs": [
        copy_format(o11["shape-14"]["paragraphs"][0], "Consumer Needs")
    ]}
    s11["shape-15"] = {"paragraphs": [
        copy_format(o11["shape-15"]["paragraphs"][0],
                    "Underserved \u2013 market fragmented with noise")
    ]}
    s11["shape-16"] = {"paragraphs": [
        copy_format(o11["shape-16"]["paragraphs"][0], "Market Situation")
    ]}
    s11["shape-17"] = {"paragraphs": [
        copy_format(o11["shape-17"]["paragraphs"][0],
                    "Govt food programs")
    ]}
    s11["shape-18"] = {"paragraphs": [
        copy_format(o11["shape-18"]["paragraphs"][0], "Sanitised")
    ]}
    s11["shape-19"] = {"paragraphs": [
        copy_format(o11["shape-19"]["paragraphs"][0],
                    "Produce sourced via govt tenders \u2013 complex process with administrative requirements")
    ]}
    s11["shape-20"] = {"paragraphs": [
        copy_format(o11["shape-20"]["paragraphs"][0], "Fresh"),
        copy_format(o11["shape-20"]["paragraphs"][1], "Traceable"),
    ]}
    s11["shape-21"] = {"paragraphs": [
        copy_format(o11["shape-21"]["paragraphs"][0],
                    "Underserved \u2013 lack of direct farm-to-govt offering")
    ]}
    s11["shape-22"] = {"paragraphs": [
        copy_format(o11["shape-22"]["paragraphs"][0],
                    "Community distribution")
    ]}
    s11["shape-23"] = {"paragraphs": [
        copy_format(o11["shape-23"]["paragraphs"][0], "Sanitised")
    ]}
    s11["shape-24"] = {"paragraphs": [
        copy_format(o11["shape-24"]["paragraphs"][0],
                    "Produce distributed via community centres, increasingly using local networks \u2013 limited experience")
    ]}
    s11["shape-25"] = {"paragraphs": [
        copy_format(o11["shape-25"]["paragraphs"][0], "Fresh"),
        copy_format(o11["shape-25"]["paragraphs"][1], "Simple and convenient"),
        copy_format(o11["shape-25"]["paragraphs"][2], "Traceability"),
    ]}
    s11["shape-26"] = {"paragraphs": [
        copy_format(o11["shape-26"]["paragraphs"][0],
                    "Underserved \u2013 infra available, but poor experience")
    ]}
    s11["shape-27"] = {"paragraphs": [
        copy_format(o11["shape-27"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s11["shape-28"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s11["shape-29"] = {"paragraphs": [
        copy_format(o11["shape-29"]["paragraphs"][0], "Fresh"),
        copy_format(o11["shape-29"]["paragraphs"][1], "Simple and convenient"),
    ]}
    s11["shape-30"] = {"paragraphs": [
        copy_format(o11["shape-30"]["paragraphs"][0],
                    "Underserved \u2013 lack of simple and direct farm-to-community offering")
    ]}
    s11["shape-31"] = {"paragraphs": [
        copy_format(o11["shape-31"]["paragraphs"][0], "Fresh"),
        copy_format(o11["shape-31"]["paragraphs"][1], "Traceable"),
    ]}
    s11["shape-32"] = {"paragraphs": [
        copy_format(o11["shape-32"]["paragraphs"][0],
                    "Underserved \u2013 lack of direct community distribution offering")
    ]}
    rep["slide-11"] = s11

    # ── slide-12: What AgriCo is / is not ──────────────────────────────
    o12 = inventory["slide-12"]
    s12 = {}
    s12["shape-0"] = {"paragraphs": [
        _p("AgriCo aims to provide a unified farming infrastructure; it is not a supermarket, distributor, or \u201canother\u201d farm")
    ]}
    s12["shape-1"] = {"paragraphs": [
        copy_format(o12["shape-1"]["paragraphs"][0],
                    "Key Functions of AgriCo")
    ]}
    s12["shape-2"] = {"paragraphs": [
        copy_format(o12["shape-2"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s12["shape-3"] = {"paragraphs": [
        copy_format(o12["shape-3"]["paragraphs"][0],
                    "AgriCo is not \u2026")
    ]}
    s12["shape-4"] = {"paragraphs": [
        copy_format(o12["shape-4"]["paragraphs"][0], "A supermarket"),
        copy_format(o12["shape-4"]["paragraphs"][1],
                    "AgriCo will not provide retail services to consumers (e.g. branded stores, consumer shelf space, etc.)"),
        copy_format(o12["shape-4"]["paragraphs"][2], "A cold-chain distributor"),
        copy_format(o12["shape-4"]["paragraphs"][3],
                    "AgriCo will not perform functions of a logistics and cold-chain distribution facility (e.g. require license from food authority)"),
        copy_format(o12["shape-4"]["paragraphs"][4],
                    "\u201cAnother\u201d farm in the market"),
        copy_format(o12["shape-4"]["paragraphs"][5],
                    "AgriCo will not add to the market fragmentation of urban farms in the country but rather to unify existing farming offerings"),
    ]}
    s12["shape-5"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s12["shape-6"] = {"paragraphs": [
        copy_format(o12["shape-6"]["paragraphs"][0],
                    "AgriCo is \u2026")
    ]}
    s12["shape-7"] = {"paragraphs": [
        copy_format(o12["shape-7"]["paragraphs"][0],
                    "An interoperable produce sourcing experience"),
        copy_format(o12["shape-7"]["paragraphs"][1],
                    "Allow buyers to source produce across a wide range of categories (e.g. vegetables, herbs, protein, specialty crops), based on unique identifiers (e.g. farm ID, batch number, crop variety)"),
        copy_format(o12["shape-7"]["paragraphs"][2],
                    "A common standard for interoperable farming"),
        copy_format(o12["shape-7"]["paragraphs"][3],
                    "A produce distribution processing service"),
        copy_format(o12["shape-7"]["paragraphs"][4],
                    "Facilitate and authenticate produce transactions between farm network users"),
        copy_format(o12["shape-7"]["paragraphs"][5],
                    "A merchant services offering"),
        copy_format(o12["shape-7"]["paragraphs"][6],
                    "Offer solutions to support day-to-day merchant sourcing and operational needs, digitising food businesses"),
    ]}
    rep["slide-12"] = s12

    # ── slide-13: Lines of service ──────────────────────────────────────
    o13 = inventory["slide-13"]
    s13 = {}
    s13["shape-0"] = {"paragraphs": [
        _p("AgriCo operates Farm Network and Distribution Platform, supported by merchant services and a standards arm")
    ]}
    s13["shape-1"] = {"paragraphs": [
        copy_format(o13["shape-1"]["paragraphs"][0], "Core Services")
    ]}
    s13["shape-2"] = {"paragraphs": [
        copy_format(o13["shape-2"]["paragraphs"][0],
                    "AgriCo's Lines of Service")
    ]}
    s13["shape-3"] = {"paragraphs": [
        copy_format(o13["shape-3"]["paragraphs"][0], "Enablers")
    ]}
    s13["shape-4"] = {"paragraphs": [
        copy_format(o13["shape-4"]["paragraphs"][0], "Farm Network")
    ]}
    s13["shape-5"] = {"paragraphs": [
        copy_format(o13["shape-5"]["paragraphs"][0],
                    "Enables multiple category produce lines (i.e. first and third party farms) and 'Produce-on-demand' / pre-order transactions"),
        copy_format(o13["shape-5"]["paragraphs"][1],
                    "Ensures interoperability between all participating entities for a wide range of produce categories (e.g. vegetables, herbs, protein, specialty crops)"),
    ]}
    s13["shape-6"] = {"paragraphs": [
        copy_format(o13["shape-6"]["paragraphs"][0], "1")
    ]}
    s13["shape-7"] = {"paragraphs": [
        copy_format(o13["shape-7"]["paragraphs"][0], "Distribution")
    ]}
    s13["shape-8"] = {"paragraphs": [
        copy_format(o13["shape-8"]["paragraphs"][0],
                    "Facilitates and authenticates produce distribution transactions"),
        copy_format(o13["shape-8"]["paragraphs"][1],
                    "Enables order processing, fulfilment, and settlement for distribution service users"),
        copy_format(o13["shape-8"]["paragraphs"][2],
                    "Sets and enforces distribution operating rules (e.g. quality management, freshness requirements)"),
    ]}
    s13["shape-9"] = {"paragraphs": [
        copy_format(o13["shape-9"]["paragraphs"][0], "2")
    ]}
    s13["shape-10"] = {"paragraphs": [
        copy_format(o13["shape-10"]["paragraphs"][0], "Merchant Services")
    ]}
    s13["shape-11"] = {"paragraphs": [
        copy_format(o13["shape-11"]["paragraphs"][0],
                    "Provides merchants with solutions that cater to day-to-day sourcing needs, including but not limited to:"),
        copy_format(o13["shape-11"]["paragraphs"][1],
                    "e-ordering and invoicing"),
        copy_format(o13["shape-11"]["paragraphs"][2],
                    "Auto inventory tracking"),
        copy_format(o13["shape-11"]["paragraphs"][3],
                    "Supplier and quality management"),
        copy_format(o13["shape-11"]["paragraphs"][4],
                    "Freshness monitoring"),
    ]}
    s13["shape-12"] = {"paragraphs": [
        copy_format(o13["shape-12"]["paragraphs"][0], "3")
    ]}
    s13["shape-13"] = {"paragraphs": [
        copy_format(o13["shape-13"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s13["shape-14"] = {"paragraphs": [
        copy_format(o13["shape-14"]["paragraphs"][0],
                    "Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s13["shape-15"] = {"paragraphs": [
        copy_format(o13["shape-15"]["paragraphs"][0], "Standards")
    ]}
    s13["shape-16"] = {"paragraphs": [
        copy_format(o13["shape-16"]["paragraphs"][0],
                    "Sets quality standard required for service users to participate in Farm Network"),
        copy_format(o13["shape-16"]["paragraphs"][1],
                    "Determines standard required for interoperability"),
        copy_format(o13["shape-16"]["paragraphs"][2],
                    "Leads initiatives to educate and shift public mindset to increase local produce adoption"),
    ]}
    s13["shape-17"] = {"paragraphs": [
        copy_format(o13["shape-17"]["paragraphs"][0], "4")
    ]}
    rep["slide-13"] = s13

    # ── slide-14: Farm Network overview ─────────────────────────────────
    o14 = inventory["slide-14"]
    s14 = {}
    s14["shape-0"] = {"paragraphs": [
        _p("The Farm Network is a unified platform that allows users to access multiple produce categories, promoting interoperability")
    ]}
    s14["shape-1"] = {"paragraphs": [
        copy_format(o14["shape-1"]["paragraphs"][0],
                    "Overview of Farm Network")
    ]}
    s14["shape-2"] = {"paragraphs": [
        copy_format(o14["shape-2"]["paragraphs"][0],
                    "Farm Network is a unified platform / 'Produce-on-demand' that enables users to access multiple produce categories, promoting interoperability and reducing fragmentation of food supply in the country")
    ]}
    s14["shape-3"] = {"paragraphs": [
        copy_format(o14["shape-3"]["paragraphs"][0], "ILLUSTRATIVE")
    ]}
    s14["shape-4"] = {"paragraphs": [
        copy_format(o14["shape-4"]["paragraphs"][0], "Farm Network")
    ]}
    s14["shape-5"] = {"paragraphs": [
        copy_format(o14["shape-5"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s14["shape-6"] = {"paragraphs": [
        copy_format(o14["shape-6"]["paragraphs"][0],
                    "Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s14["shape-7"] = {"paragraphs": [
        copy_format(o14["shape-7"]["paragraphs"][0], "How does it work?")
    ]}
    s14["shape-8"] = {"paragraphs": [
        copy_format(o14["shape-8"]["paragraphs"][0],
                    "Produce category providers register to participate in Farm Network to enhance their respective distribution with wide access and interoperability"),
        copy_format(o14["shape-8"]["paragraphs"][1],
                    "Consumers browse their preferred produce categories on the Farm Network platform (e.g. vegetables, herbs, protein, specialty crops)"),
        copy_format(o14["shape-8"]["paragraphs"][2],
                    "Consumers select the most preferred source of produce to complete an order (e.g. organic greens from a vertical farm)"),
        copy_format(o14["shape-8"]["paragraphs"][3],
                    "Consumers receive produce (direct delivery or collection) through mode offered by merchants (e.g. neighbourhood pickup, home delivery, market stall), enabled by 'Produce-on-demand'"),
    ]}
    s14["shape-9"] = {"paragraphs": [
        copy_format(o14["shape-9"]["paragraphs"][0], "1")
    ]}
    s14["shape-10"] = {"paragraphs": [
        copy_format(o14["shape-10"]["paragraphs"][0], "Vegetables")
    ]}
    s14["shape-11"] = {"paragraphs": [
        copy_format(o14["shape-11"]["paragraphs"][0], "Herbs")
    ]}
    s14["shape-12"] = {"paragraphs": [
        copy_format(o14["shape-12"]["paragraphs"][0], "2")
    ]}
    s14["shape-13"] = {"paragraphs": [
        copy_format(o14["shape-13"]["paragraphs"][0], "Protein")
    ]}
    s14["shape-14"] = {"paragraphs": [
        copy_format(o14["shape-14"]["paragraphs"][0], "Who does it serve?")
    ]}
    s14["shape-15"] = {"paragraphs": [
        copy_format(o14["shape-15"]["paragraphs"][0],
                    "Service users (i.e. produce category providers) who compete on freshness and variety on their respective platforms (e.g. farm-to-table, organic certification)"),
        copy_format(o14["shape-15"]["paragraphs"][1],
                    "Consumers who want to access fresh local produce across a wide range of categories and distribution channels"),
    ]}
    s14["shape-16"] = {"paragraphs": [
        copy_format(o14["shape-16"]["paragraphs"][0], "3")
    ]}
    s14["shape-17"] = {"paragraphs": [
        copy_format(o14["shape-17"]["paragraphs"][0], "Specialty")
    ]}
    s14["shape-18"] = {"paragraphs": [
        copy_format(o14["shape-18"]["paragraphs"][0], "4")
    ]}
    rep["slide-14"] = s14

    # ── slide-15: Distribution overview ─────────────────────────────────
    o15 = inventory["slide-15"]
    s15 = {}
    s15["shape-0"] = {"paragraphs": [
        _p("AgriCo will allow 3rd party producers to participate in an open distribution scheme")
    ]}
    s15["shape-1"] = {"paragraphs": [
        copy_format(o15["shape-1"]["paragraphs"][0],
                    "Overview of Distribution")
    ]}
    s15["shape-2"] = {"paragraphs": [
        copy_format(o15["shape-2"]["paragraphs"][0],
                    "Distribution facilitates and authenticates produce orders, enables processing, fulfilment, and settlement services, as well as sets and enforces distribution operating rules")
    ]}
    s15["shape-3"] = {"paragraphs": [
        copy_format(o15["shape-3"]["paragraphs"][0], "ILLUSTRATIVE")
    ]}
    s15["shape-4"] = {"paragraphs": [
        copy_format(o15["shape-4"]["paragraphs"][0], "1")
    ]}
    s15["shape-5"] = {"paragraphs": [
        copy_format(o15["shape-5"]["paragraphs"][0], "Service User")
    ]}
    s15["shape-6"] = {"paragraphs": [
        copy_format(o15["shape-6"]["paragraphs"][0], "2")
    ]}
    s15["shape-7"] = {"paragraphs": [
        copy_format(o15["shape-7"]["paragraphs"][0], "Interface")
    ]}
    s15["shape-8"] = {"paragraphs": [
        copy_format(o15["shape-8"]["paragraphs"][0], "How does it work?")
    ]}
    s15["shape-9"] = {"paragraphs": [
        copy_format(o15["shape-9"]["paragraphs"][0],
                    "Service user integrates and joins the distribution platform to leverage on the digital infrastructure provided by AgriCo"),
        copy_format(o15["shape-9"]["paragraphs"][1],
                    "Interface facilitates all orders processed by service users within the distribution network"),
        copy_format(o15["shape-9"]["paragraphs"][2],
                    "Enables fulfilment and settlement services \u2013 potentially leverage on existing cold-chain infrastructure"),
    ]}
    s15["shape-10"] = {"paragraphs": [
        copy_format(o15["shape-10"]["paragraphs"][0], "1")
    ]}
    s15["shape-11"] = {"paragraphs": [
        copy_format(o15["shape-11"]["paragraphs"][0], "3")
    ]}
    s15["shape-12"] = {"paragraphs": [
        copy_format(o15["shape-12"]["paragraphs"][0], "Herbs")
    ]}
    s15["shape-13"] = {"paragraphs": [
        copy_format(o15["shape-13"]["paragraphs"][0], "Protein")
    ]}
    s15["shape-14"] = {"paragraphs": [
        copy_format(o15["shape-14"]["paragraphs"][0], "2")
    ]}
    s15["shape-15"] = {"paragraphs": [
        copy_format(o15["shape-15"]["paragraphs"][0], "3")
    ]}
    s15["shape-16"] = {"paragraphs": [
        copy_format(o15["shape-16"]["paragraphs"][0],
                    "AgriCo Distribution")
    ]}
    s15["shape-17"] = {"paragraphs": [
        copy_format(o15["shape-17"]["paragraphs"][0],
                    "Fulfilment & Settlement")
    ]}
    s15["shape-18"] = {"paragraphs": [
        copy_format(o15["shape-18"]["paragraphs"][0], "Vegetables")
    ]}
    s15["shape-19"] = {"paragraphs": [
        copy_format(o15["shape-19"]["paragraphs"][0], "Specialty")
    ]}
    s15["shape-20"] = {"paragraphs": [
        copy_format(o15["shape-20"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s15["shape-21"] = {"paragraphs": [
        copy_format(o15["shape-21"]["paragraphs"][0],
                    "Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s15["shape-22"] = {"paragraphs": [
        copy_format(o15["shape-22"]["paragraphs"][0], "Who does it serve?")
    ]}
    s15["shape-23"] = {"paragraphs": [
        copy_format(o15["shape-23"]["paragraphs"][0],
                    "Service users (i.e. produce category providers) who want to leverage on AgriCo's digital infrastructure to achieve interoperability, extend customer reach, and distribution experience")
    ]}
    rep["slide-15"] = s15

    # ── slide-16: Merchant services ─────────────────────────────────────
    o16 = inventory["slide-16"]
    s16 = {}
    s16["shape-0"] = {"paragraphs": [
        _p("Merchants could leverage on AgriCo's digital solutions to support day-to-day sourcing and operational needs")
    ]}
    s16["shape-1"] = {"paragraphs": [
        copy_format(o16["shape-1"]["paragraphs"][0],
                    "Overview of Merchant Services")
    ]}
    s16["shape-2"] = {"paragraphs": [
        copy_format(o16["shape-2"]["paragraphs"][0],
                    "Merchant services enable overlay digital solutions that cater to merchants' day-to-day sourcing and operational needs")
    ]}
    s16["shape-3"] = {"paragraphs": [
        copy_format(o16["shape-3"]["paragraphs"][0], "ILLUSTRATIVE")
    ]}
    s16["shape-4"] = {"paragraphs": [
        copy_format(o16["shape-4"]["paragraphs"][0], "How does it work?")
    ]}
    s16["shape-5"] = {"paragraphs": [
        copy_format(o16["shape-5"]["paragraphs"][0],
                    "Merchants adopt AgriCo's offering, sourcing most or all produce via AgriCo's network"),
        copy_format(o16["shape-5"]["paragraphs"][1],
                    "Merchants leverage on AgriCo to enable digital sourcing solutions to support business operations"),
        copy_format(o16["shape-5"]["paragraphs"][2],
                    "AgriCo enables and integrates selected digital solutions for merchants"),
    ]}
    s16["shape-6"] = {"paragraphs": [
        copy_format(o16["shape-6"]["paragraphs"][0], "1")
    ]}
    s16["shape-7"] = {"paragraphs": [
        copy_format(o16["shape-7"]["paragraphs"][0], "2")
    ]}
    s16["shape-8"] = {"paragraphs": [
        copy_format(o16["shape-8"]["paragraphs"][0],
                    "Merchant Services \u2013 Overlay Digital Solutions")
    ]}
    s16["shape-9"] = {"paragraphs": [
        copy_format(o16["shape-9"]["paragraphs"][0], "3")
    ]}
    s16["shape-10"] = {"paragraphs": [
        copy_format(o16["shape-10"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s16["shape-11"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s16["shape-12"] = {"paragraphs": [
        copy_format(o16["shape-12"]["paragraphs"][0], "Who does it serve?")
    ]}
    s16["shape-13"] = {"paragraphs": [
        copy_format(o16["shape-13"]["paragraphs"][0],
                    "Merchants, onboarded by AgriCo, who want to digitise their sourcing and business operations, enabling operational efficiency (e.g. e-ordering and invoicing, auto inventory tracking, supplier management, freshness monitoring, reporting and analytics)")
    ]}
    rep["slide-16"] = s16

    # ── slide-17: Standards ─────────────────────────────────────────────
    o17 = inventory["slide-17"]
    s17 = {}
    s17["shape-0"] = {"paragraphs": [
        _p("Standards set requirements for Farm Network and Distribution to drive quality and traceability for consumers and merchants")
    ]}
    s17["shape-1"] = {"paragraphs": [
        copy_format(o17["shape-1"]["paragraphs"][0],
                    "Overview of Standards")
    ]}
    s17["shape-2"] = {"paragraphs": [
        copy_format(o17["shape-2"]["paragraphs"][0],
                    "Standards set technical, quality, and operational requirements for Farm Network service users, determines and enforces distribution rules, as well as boost consumer and merchant adoption")
    ]}
    s17["shape-3"] = {"paragraphs": [
        copy_format(o17["shape-3"]["paragraphs"][0], "ILLUSTRATIVE")
    ]}
    s17["shape-4"] = {"paragraphs": [
        copy_format(o17["shape-4"]["paragraphs"][0], "Who does it relate to?")
    ]}
    s17["shape-5"] = {"paragraphs": [
        copy_format(o17["shape-5"]["paragraphs"][0],
                    "Farm Network service user (i.e. produce category providers) \u2013 subjected to farming standards"),
        copy_format(o17["shape-5"]["paragraphs"][1],
                    "Distribution service user \u2013 subjected to distribution rules"),
        copy_format(o17["shape-5"]["paragraphs"][2],
                    "AgriCo's consumers and merchants"),
    ]}
    s17["shape-6"] = {"paragraphs": [
        copy_format(o17["shape-6"]["paragraphs"][0], "How does it work?")
    ]}
    s17["shape-7"] = {"paragraphs": [
        copy_format(o17["shape-7"]["paragraphs"][0],
                    "Farm Network service user must meet the set technical, quality, and operational requirements to participate in Farm Network"),
        copy_format(o17["shape-7"]["paragraphs"][1],
                    "Distribution service user must adhere to distribution rules set by AgriCo"),
        copy_format(o17["shape-7"]["paragraphs"][2],
                    "AgriCo's offering to align to formal and informal consumer and merchant adoption levers to change public mindset and behavior towards local produce"),
    ]}
    s17["shape-8"] = {"paragraphs": [
        copy_format(o17["shape-8"]["paragraphs"][0],
                    "Source: PwC Strategy& analysis")
    ]}
    s17["shape-9"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    s17["shape-10"] = {"paragraphs": [
        copy_format(o17["shape-10"]["paragraphs"][0], "AgriCo Standards")
    ]}
    rep["slide-17"] = s17

    # ── slide-18: Business case ─────────────────────────────────────────
    o18 = inventory["slide-18"]
    s18 = {}
    s18["shape-0"] = {"paragraphs": [
        _p("The target addressable market for AgriCo was identified and business case developed to substantiate the investment required")
    ]}
    s18["shape-1"] = {"paragraphs": [
        copy_format(o18["shape-1"]["paragraphs"][0],
                    "Overview of the Target Addressable Market")
    ]}
    s18["shape-2"] = {"paragraphs": [
        copy_format(o18["shape-2"]["paragraphs"][0],
                    "Overview of the Business Case")
    ]}
    s18["shape-3"] = {"paragraphs": [
        copy_format(o18["shape-3"]["paragraphs"][0], "Key Takeaways"),
        copy_format(o18["shape-3"]["paragraphs"][1],
                    "AgriCo will be competing in the imported produce market in its initial phase \u2013 capture rate is driven by AgriCo's interoperability feature and its position as the top-of-mind local produce platform"),
        copy_format(o18["shape-3"]["paragraphs"][2],
                    "AgriCo will capture wholesale fresh produce transactions subsequently as merchants move from imported to locally-sourced ingredients"),
        copy_format(o18["shape-3"]["paragraphs"][3],
                    "Specialty and premium import transactions will not be captured by AgriCo as they offer consumers a different product proposition to AgriCo, competing in a different market"),
    ]}
    s18["shape-4"] = {"paragraphs": [
        copy_format(o18["shape-4"]["paragraphs"][0], "Key Takeaways"),
        copy_format(o18["shape-4"]["paragraphs"][1],
                    "As a national infrastructure, AgriCo's fees to service users will be lower than local and international produce distributors \u2013 main revenue lines include the farm network, distribution and membership fee"),
        copy_format(o18["shape-4"]["paragraphs"][2],
                    "AgriCo Farm Network will be in direct competition with imported produce distributors and emerging AgriTech platforms at steady state"),
        copy_format(o18["shape-4"]["paragraphs"][3],
                    "AgriCo's cost buckets are categorised into Plan, Build, Engage, Operate and Change \u2013 largest in Build as capital is required to develop the farm network infrastructure and directory required to enable interoperability"),
    ]}
    s18["shape-5"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    rep["slide-18"] = s18

    # ── slide-19: Operating model ───────────────────────────────────────
    o19 = inventory["slide-19"]
    s19 = {}
    s19["shape-0"] = {"paragraphs": [
        _p("AgriCo's operating model and corporate structure were developed in order to maximise synergies between the Clients")
    ]}
    s19["shape-1"] = {"paragraphs": [
        copy_format(o19["shape-1"]["paragraphs"][0],
                    "Overview of the Operating Model")
    ]}
    s19["shape-2"] = {"paragraphs": [
        copy_format(o19["shape-2"]["paragraphs"][0],
                    "Overview of the Corporate Structure")
    ]}
    s19["shape-3"] = {"paragraphs": [
        copy_format(o19["shape-3"]["paragraphs"][0], "Key Takeaways"),
        copy_format(o19["shape-3"]["paragraphs"][1],
                    "A hybrid (cross) model of a Business Unit-led and Functions-led operating model is recommended for AgriCo as support services are centralised and redundancies are avoided"),
        copy_format(o19["shape-3"]["paragraphs"][2],
                    "AgriCo's target operating model is aimed to be lean and equipped with essential \u201crun\u201d function for AgriCo's service offering, \u201cchange\u201d function for products and innovation, and \u201cenable\u201d function for farm technology management and enterprise functions"),
    ]}
    s19["shape-4"] = {"paragraphs": [
        copy_format(o19["shape-4"]["paragraphs"][0], "Key Takeaways"),
        copy_format(o19["shape-4"]["paragraphs"][1],
                    "AgriCo is recommended to be a private company as it allows for independence, swift changes without ministerial approvals, and limited risks for AgriCo"),
        copy_format(o19["shape-4"]["paragraphs"][2],
                    "As a public infrastructure, AgriCo's Board of Directors will include a chairman, executive directors, shareholder representatives and independent board members from various backgrounds to uphold unbiased decision making"),
    ]}
    s19["shape-5"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    rep["slide-19"] = s19

    # ── slide-20: Technical architecture ────────────────────────────────
    o20 = inventory["slide-20"]
    s20 = {}
    s20["shape-0"] = {"paragraphs": [
        _p("The high level technical architecture and implementation roadmap were developed to aid implementation of AgriCo")
    ]}
    s20["shape-1"] = {"paragraphs": [
        copy_format(o20["shape-1"]["paragraphs"][0],
                    "Overview of the Technical Architecture")
    ]}
    s20["shape-2"] = {"paragraphs": [
        copy_format(o20["shape-2"]["paragraphs"][0],
                    "Overview of the Implementation Roadmap")
    ]}
    s20["shape-3"] = {"paragraphs": [
        copy_format(o20["shape-3"]["paragraphs"][0], "Key Takeaways"),
        copy_format(o20["shape-3"]["paragraphs"][1],
                    "AgriCo services to include capturing produce orders, transmitting messages, and verifying and authenticating transactions to facilitating fulfilment and settlement"),
        copy_format(o20["shape-3"]["paragraphs"][2],
                    "To capture produce orders, AgriCo will leverage on existing channels (i.e. mobile app) and greenfield (i.e. IoT sensors) in order to maximise affordability, availability, scalability and traceability"),
        copy_format(o20["shape-3"]["paragraphs"][3],
                    "AgriCo will provide a seamless farm-to-table experience which includes human-to-system and system-to-system interaction"),
    ]}
    s20["shape-4"] = {"paragraphs": [
        copy_format(o20["shape-4"]["paragraphs"][0], "Key Takeaways"),
        copy_format(o20["shape-4"]["paragraphs"][1],
                    "As a public infrastructure, an integrated go-live model was recommended for AgriCo as stakeholder socialisation and testing runs in parallel with the traditional plan, build and run"),
        copy_format(o20["shape-4"]["paragraphs"][2],
                    "Go-live for AgriCo will be fast-to-market, potentially ahead of emerging AgriTech competition"),
        copy_format(o20["shape-4"]["paragraphs"][3],
                    "Flexibility in making operational refinements"),
        copy_format(o20["shape-4"]["paragraphs"][4],
                    "Support from key stakeholders in the early stages is crucial to ensure the success of AgriCo"),
    ]}
    s20["shape-5"] = {"paragraphs": [
        _p("Confidential information for the sole benefit and use of PwC's client.")
    ]}
    rep["slide-20"] = s20

    # ── slide-21: Closing ───────────────────────────────────────────────
    o21 = inventory["slide-21"]
    s21 = {}
    s21["shape-0"] = {"paragraphs": [
        copy_format(o21["shape-0"]["paragraphs"][0],
                    "\u00a9 2025 PwC. All rights reserved."),
        copy_format(o21["shape-0"]["paragraphs"][1],
                    "PwC refers to the PwC network and/or one or more of its member firms, each of which is a separate legal entity. Please see www.pwc.com/structure for further details."),
    ]}
    s21["shape-1"] = {"paragraphs": [
        copy_format(o21["shape-1"]["paragraphs"][0],
                    "Strategy       Impact")
    ]}
    rep["slide-21"] = s21

    return rep


def main():
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    replacement = build_replacement(inventory)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(replacement, f, indent=2, ensure_ascii=False)

    print(f"Replacement JSON written to {OUTPUT_PATH}")
    print(f"  Slides: {len(replacement)}")
    total_shapes = sum(len(v) for v in replacement.values())
    print(f"  Total shapes: {total_shapes}")


if __name__ == "__main__":
    main()
