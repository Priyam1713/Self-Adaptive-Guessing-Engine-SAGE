"""Hierarchical occupational taxonomy: sector -> field -> occupation.

Design
------
QUESTIONS maps question id -> (default, text). `default` is the prior
probability that a *random* career answers "yes". General behavioral
questions default near 0.5; domain questions (aircraft? lab? courtroom?)
default near 0 - so a career only needs to override the handful of
attributes that make it unusual. That is what makes hundreds of niche
occupations tractable to author and extend.

T is the taxonomy tree. Each sector and field carries an "a" (attributes)
block that all descendants inherit; leaves override the few attributes that
distinguish them from their siblings. compile() flattens inheritance into
per-occupation profiles.

Answer probabilities are starting beliefs only - gameplay updates them.
"""

QUESTIONS = {
    # -- employment status ---------------------------------------------------
    "paid_work":    (.97, "Do you currently earn money from working?"),
    "student_now":  (.02, "Are you currently a student or trainee?"),
    "retired_now":  (.01, "Have you retired from working life?"),
    "home_family":  (.02, "Do you spend most of your time caring for your home or family?"),
    # -- broad work style ----------------------------------------------------
    "indoors":      (.5,  "Do you work mostly indoors?"),
    "degree":       (.5,  "Does your role typically require a university degree?"),
    "long_training":(.3,  "Did your role require more than 5 years of study or training?"),
    "screen":       (.5,  "Do you spend most of your workday at a computer screen?"),
    "office":       (.4,  "Do you work in an office setting?"),
    "public":       (.5,  "Do you deal directly with customers, clients, or the public most days?"),
    "people_core":  (.4,  "Is helping or serving specific individual people the core of your work?"),
    "data_info":    (.45, "Is your work mainly about information, data, or documents (rather than physical things)?"),
    "make_physical":(.2,  "Do you make, build, grow, or repair physical things?"),
    "hands":        (.35, "Do you mainly work with your hands?"),
    "physical":     (.3,  "Is your work physically demanding?"),
    "tools":        (.25, "Do you regularly use tools, machinery, or specialist equipment?"),
    "machines_op":  (.08, "Is operating a large machine or vehicle your main task?"),
    "uniform":      (.25, "Do you wear a uniform or protective clothing at work?"),
    "danger":       (.12, "Is your work considered dangerous or high-risk?"),
    "emergency":    (.05, "Do you respond to emergencies as part of your work?"),
    "enforce":      (.06, "Does your work involve enforcing laws, rules, or safety?"),
    "nine2five":    (.5,  "Do you mostly work regular daytime hours?"),
    "shifts":       (.3,  "Do you often work nights, weekends, or irregular shifts?"),
    "high_pay":     (.4,  "Do you earn more than the average national salary?"),
    "manage":       (.25, "Do you manage or supervise other people as a core duty?"),
    "teach":        (.1,  "Is teaching or training others a core part of your work?"),
    "children":     (.06, "Do you work primarily with children?"),
    "creative":     (.2,  "Is your work primarily creative or artistic?"),
    "content":      (.1,  "Do you create content (writing, video, audio, images) for an audience?"),
    "perform":      (.04, "Do you perform in front of an audience or camera?"),
    "writing":      (.15, "Is writing text a major part of your work?"),
    "speaking":     (.12, "Is presenting or speaking to groups a major part of your work?"),
    "numbers":      (.3,  "Does your work involve a lot of numbers or money?"),
    "adv_math":     (.1,  "Does your work require advanced mathematics or statistics?"),
    "money_others": (.06, "Do you manage, invest, or advise on other people's money?"),
    "sales":        (.12, "Is selling things a core part of your work?"),
    "market_promo": (.08, "Is promoting products, brands, or ideas part of your work?"),
    "clients_biz":  (.3,  "Are your clients mainly businesses or organizations rather than individuals?"),
    "government":   (.18, "Do you work for the government or public sector?"),
    "military":     (.015,"Are you part of the armed forces?"),
    "politics":     (.02, "Is your work related to politics or policy-making?"),
    "legal":        (.06, "Does your work involve laws, contracts, or legal documents?"),
    "courtroom":    (.02, "Do you appear in courtrooms as part of your work?"),
    "travel":       (.18, "Does your work regularly take you to different sites, cities, or countries?"),
    "driving":      (.07, "Is driving or piloting a vehicle a significant part of your work?"),
    "self_emp":     (.2,  "Are people in your role commonly self-employed or freelance?"),
    "science":      (.1,  "Does your work involve science?"),
    "lab":          (.04, "Do you work in a laboratory?"),
    "research":     (.12, "Is doing research a major part of your work?"),
    "living":       (.1,  "Does your work focus on living things (people's bodies, animals, or plants)?"),
    "healthcare":   (.05, "Do you work in the healthcare field?"),
    "patients":     (.04, "Do you personally examine or treat patients?"),
    "prescribe":    (.015,"Can people in your role prescribe medicine?"),
    "surgery":      (.01, "Do you perform surgery or invasive procedures?"),
    "mental_health":(.025,"Do you mainly help people with mental or emotional wellbeing?"),
    "body_part":    (.015,"Do you specialize in one part of the body (like teeth, eyes, heart, or feet)?"),
    "serious_ill":  (.03, "Do you mainly deal with serious or life-threatening conditions?"),
    "births":       (.005,"Do you help bring babies into the world?"),
    "care_daily":   (.03, "Do you help people with daily living (washing, feeding, mobility)?"),
    "fit_sport":    (.03, "Is your work related to sport or physical fitness?"),
    "code":         (.06, "Do you write computer code as a core part of your work?"),
    "software":     (.07, "Do you build or maintain software or IT systems?"),
    "hardware":     (.04, "Do you work with electronic devices, circuits, or hardware?"),
    "cyber":        (.015,"Do you protect computer systems or data from attacks?"),
    "games":        (.01, "Is your work related to video games?"),
    "engineer_id":  (.06, "Would the word 'engineer' appear in your job title?"),
    "vehicles":     (.04, "Does your work center on vehicles or craft (cars, aircraft, ships, trains)?"),
    "aircraft":     (.012,"Does your work involve aircraft or spacecraft?"),
    "ships":        (.012,"Does your work involve ships, boats, or the sea?"),
    "rail":         (.006,"Does your work involve trains or railways?"),
    "engines":      (.01, "Do you work on engines, motors, or propulsion systems?"),
    "energy":       (.025,"Does your work involve energy, power, or fuel systems?"),
    "buildings":    (.05, "Does your work center on buildings, roads, or construction sites?"),
    "electric_wire":(.015,"Does your work primarily involve electrical systems or wiring?"),
    "pipes":        (.01, "Does your work involve water pipes, drains, or heating systems?"),
    "fix_repair":   (.07, "Is repairing or maintaining things a core part of your work?"),
    "factory":      (.04, "Do you work in a factory or production plant?"),
    "mining":       (.008,"Does your work involve mining, drilling, or extracting resources?"),
    "crops":        (.015,"Do you grow crops or plants for a living?"),
    "animals":      (.02, "Do you work with animals?"),
    "food_domain":  (.05, "Is your work related to food or drink?"),
    "cook":         (.02, "Do you cook or prepare food or drinks yourself?"),
    "hospitality":  (.04, "Do you work in hotels, restaurants, bars, or tourism?"),
    "beauty":       (.015,"Does your work involve beauty, grooming, or personal appearance?"),
    "fashion":      (.015,"Is your work related to clothing or fashion?"),
    "music_dom":    (.015,"Is your work primarily about music?"),
    "visual":       (.05, "Is your output primarily visual (images, video, or designs)?"),
    "film_stage":   (.015,"Do you work in film, TV, or theater?"),
    "news_media":   (.02, "Do you work in news or media?"),
    "finance_ind":  (.05, "Do you work in the finance, banking, or insurance industry?"),
    "property":     (.015,"Is your work related to buying, selling, or renting property?"),
    "hist_culture": (.012,"Does your work involve history, culture, or artifacts?"),
    "language_dom": (.015,"Does your work center on languages or translation?"),
    "earth_env":    (.025,"Does your work involve the earth, weather, oceans, or environment?"),
    "religion":     (.008,"Is your work connected to religion or spiritual practice?"),
    "teach_higher": (.02, "Do you teach at university or college level?"),
    "protect":      (.06, "Is protecting people or property central to your work?"),
    "design":       (.1,  "Do you design things (structures, products, visuals, or systems)?"),
    # -- niche discriminators (fire only once the field has narrowed) --------
    "eyes":         (.004,"Is your work focused on eyes or eyesight?"),
    "teeth":        (.004,"Is your work focused on teeth or the mouth?"),
    "feet":         (.003,"Is your work focused on feet?"),
    "hearing":      (.003,"Is your work focused on hearing or ears?"),
    "spine_joints": (.004,"Do you treat people by working on their muscles, spine, or joints?"),
    "anesthesia":   (.002,"Do you put patients to sleep or manage pain for operations?"),
    "addiction":    (.003,"Do you mainly help people with addictions?"),
    "comms_net":    (.01, "Does your work involve communication networks (phone or internet infrastructure)?"),
    "chemicals":    (.015,"Do you work with chemicals or chemical processes?"),
    "mobile":       (.005,"Is your work focused on mobile apps?"),
    "data_work":    (.012,"Is your work mainly about analyzing or managing data (rather than building products)?"),
    "ml_ai":        (.008,"Do you build AI or machine learning systems?"),
    "servers":      (.01, "Do you keep servers, networks, or IT systems running for others?"),
    "test_qa":      (.008,"Is testing or quality-checking things your main responsibility?"),
    "crypto":       (.003,"Does your work involve cryptocurrency or blockchain?"),
    "microbes":     (.005,"Do you study cells or microscopic organisms?"),
    "genes":        (.005,"Is your work about genes or DNA?"),
    "plants":       (.008,"Does your work focus on plants or growing things?"),
    "rocks":        (.005,"Does your work involve rocks, minerals, or drilling into the ground?"),
    "pollution":    (.01, "Is your work about pollution, conservation, or protecting nature?"),
    "young_kids":   (.01, "Do you mainly work with children under about six years old?"),
    "disabilities": (.01, "Do you mainly support people with disabilities or special needs?"),
    "taxes":        (.008,"Is your work mainly about taxes?"),
    "payroll":      (.004,"Is your work mainly about paying employees or payroll?"),
    "trading":      (.005,"Do you personally buy and sell investments as your job?"),
    "loans":        (.006,"Is your work mainly about loans, credit, or mortgages?"),
    "insurance":    (.012,"Do you work in insurance?"),
    "hiring":       (.008,"Is your work about hiring people or employee matters?"),
    "projects_temp":(.05, "Do you run time-limited projects rather than ongoing operations?"),
    "shipping":     (.01, "Does your work involve moving goods, packages, or freight?"),
    "seo_web":      (.004,"Do you optimize websites to rank higher in search engines?"),
    "photos":       (.004,"Do you take photographs professionally?"),
    "video_anim":   (.01, "Do you work with video or animation?"),
    "drawing":      (.006,"Do you draw or illustrate as part of your work?"),
    "events_org":   (.008,"Do you organize events like weddings, parties, or conferences?"),
    "alcohol":      (.008,"Does your work involve alcoholic drinks?"),
    "water":        (.008,"Does your work take place in or around water?"),
    "heights":      (.01, "Do you regularly work at heights (roofs, towers, scaffolding)?"),
    "wood":         (.006,"Do you work mainly with wood?"),
    "stone_brick":  (.005,"Do you work mainly with bricks, stone, or concrete?"),
    "glass":        (.004,"Do you work mainly with glass?"),
    "precious":     (.003,"Do you work with precious metals, gems, or jewelry?"),
    "hair":         (.004,"Do you cut, style, or color hair?"),
    "nails_skin":   (.005,"Is your work about skin care, nails, or cosmetic treatments?"),
    "death":        (.003,"Does your work involve death or funerals?"),
    "sew":          (.004,"Do you sew or make clothing?"),
    "metal":        (.01, "Do you work mainly with metal?"),
    "clean":        (.012,"Is cleaning things a core part of your work?"),
}

T = {

# =========================================================================
"not currently employed": {
  "a": {"paid_work": .04, "uniform": .03, "manage": .05, "sales": .02,
        "clients_biz": .03, "high_pay": .08, "office": .08, "public": .3,
        "nine2five": .3, "screen": .4, "shifts": .1, "teach": .03,
        "data_info": .2, "people_core": .2, "travel": .1, "self_emp": .05,
        "numbers": .1, "tools": .05, "degree": .4, "enforce": .01},
  "fields": {
    "not employed": {
      "a": {},
      "leaves": {
        "unemployed (looking for work)": {"student_now": .1, "screen": .6, "writing": .3, "indoors": .8},
        "student": {"student_now": .97, "screen": .75, "writing": .6, "indoors": .85, "degree": .6, "nine2five": .55, "teach_higher": .1},
        "retired person": {"retired_now": .97, "indoors": .7, "nine2five": .4, "screen": .2},
        "homemaker / stay-at-home parent": {"home_family": .97, "care_daily": .8, "cook": .75, "children": .7,
                                            "physical": .5, "indoors": .9, "food_domain": .3, "hands": .5},
      },
    },
  },
},

# =========================================================================
"healthcare & medicine": {
  "a": {"healthcare": .97, "people_core": .9, "public": .85, "indoors": .92,
        "living": .9, "patients": .8, "degree": .7, "uniform": .6,
        "science": .4, "shifts": .55, "nine2five": .4, "emergency": .3,
        "data_info": .2, "hands": .5, "serious_ill": .3, "high_pay": .55,
        "make_physical": .03, "sales": .02, "creative": .03, "screen": .3},
  "fields": {
    "physicians & specialists": {
      "a": {"patients": .95, "degree": .97, "long_training": .95, "high_pay": .9,
            "prescribe": .92, "science": .6, "manage": .4, "adv_math": .2},
      "leaves": {
        "general practitioner / family doctor": {"nine2five": .7, "children": .4, "emergency": .2, "surgery": .05, "serious_ill": .2},
        "surgeon": {"surgery": .98, "hands": .85, "high_pay": .97, "shifts": .7, "serious_ill": .7, "emergency": .5},
        "anesthesiologist": {"anesthesia": .97, "surgery": .5, "emergency": .7, "high_pay": .97, "serious_ill": .7, "hands": .5, "public": .6},
        "psychiatrist": {"mental_health": .97, "surgery": .01, "nine2five": .7, "hands": .1, "serious_ill": .4},
        "pediatrician": {"children": .97, "surgery": .05, "nine2five": .6, "serious_ill": .25},
        "cardiologist": {"body_part": .95, "serious_ill": .7, "surgery": .4, "emergency": .6},
        "oncologist": {"serious_ill": .97, "surgery": .1, "research": .4, "nine2five": .6, "emergency": .3},
        "radiologist": {"screen": .9, "patients": .3, "public": .3, "surgery": .05, "hands": .2, "emergency": .2},
        "emergency physician": {"emergency": .98, "shifts": .95, "nine2five": .05, "serious_ill": .85, "surgery": .3},
        "dermatologist": {"body_part": .95, "nine2five": .85, "surgery": .2, "emergency": .03, "serious_ill": .1},
        "obstetrician-gynecologist": {"births": .95, "surgery": .7, "shifts": .8, "body_part": .8, "emergency": .6},
      },
    },
    "nursing & midwifery": {
      "a": {"patients": .95, "uniform": .95, "degree": .6, "long_training": .3,
            "high_pay": .45, "physical": .6, "care_daily": .6, "shifts": .85,
            "nine2five": .2, "hands": .7, "emergency": .5, "prescribe": .1},
      "leaves": {
        "registered nurse": {"serious_ill": .4},
        "intensive care (ICU) nurse": {"serious_ill": .92, "emergency": .8, "tools": .5},
        "midwife": {"births": .97, "children": .3, "serious_ill": .2, "emergency": .6},
        "nurse practitioner": {"prescribe": .8, "degree": .85, "nine2five": .5, "care_daily": .3, "long_training": .6},
      },
    },
    "dental care": {
      "a": {"body_part": .97, "teeth": .97, "patients": .93, "uniform": .9, "nine2five": .85,
            "indoors": .97, "hands": .9, "emergency": .05, "shifts": .08, "serious_ill": .05},
      "leaves": {
        "dentist": {"degree": .95, "long_training": .85, "high_pay": .9, "prescribe": .6, "manage": .6, "surgery": .4},
        "orthodontist": {"degree": .97, "long_training": .95, "high_pay": .95, "children": .55, "surgery": .1, "prescribe": .3},
        "dental hygienist": {"degree": .4, "long_training": .05, "high_pay": .4, "surgery": .05, "manage": .05},
      },
    },
    "allied health & therapy": {
      "a": {"patients": .9, "degree": .7, "nine2five": .6, "uniform": .55,
            "emergency": .1, "shifts": .3, "serious_ill": .15, "prescribe": .05},
      "leaves": {
        "physiotherapist": {"physical": .7, "hands": .93, "spine_joints": .7, "fit_sport": .5, "care_daily": .4},
        "occupational therapist": {"care_daily": .85, "hands": .5, "teach": .4},
        "speech therapist": {"children": .6, "teach": .5, "language_dom": .3, "hands": .1},
        "radiographer / imaging technician": {"screen": .7, "tools": .7, "hardware": .3, "uniform": .9, "shifts": .5},
        "paramedic": {"emergency": .98, "driving": .85, "shifts": .95, "uniform": .97, "nine2five": .05,
                      "danger": .5, "serious_ill": .85, "degree": .35, "machines_op": .3, "vehicles": .3},
        "optometrist": {"body_part": .97, "eyes": .97, "prescribe": .5, "sales": .3, "manage": .5, "nine2five": .85},
        "audiologist": {"body_part": .9, "hearing": .95, "hardware": .4, "nine2five": .85},
        "dietitian / nutritionist": {"food_domain": .7, "teach": .5, "nine2five": .8, "hands": .1},
        "podiatrist": {"body_part": .97, "feet": .97, "surgery": .3, "nine2five": .85, "self_emp": .4},
        "chiropractor": {"hands": .95, "spine_joints": .95, "body_part": .7, "self_emp": .6, "nine2five": .8},
      },
    },
    "pharmacy & medical laboratory": {
      "a": {"science": .65, "nine2five": .6, "uniform": .8, "emergency": .05},
      "leaves": {
        "pharmacist": {"patients": .6, "public": .9, "prescribe": .3, "sales": .4, "degree": .9,
                       "high_pay": .7, "numbers": .4, "manage": .5},
        "medical laboratory technician": {"lab": .95, "patients": .15, "public": .1, "screen": .5,
                                          "degree": .5, "hands": .6, "shifts": .4},
        "pathologist": {"lab": .9, "degree": .97, "long_training": .95, "patients": .1, "public": .1,
                        "high_pay": .9, "serious_ill": .6, "research": .4, "prescribe": .3,
                        "death": .4, "microbes": .5},
        "embryologist": {"lab": .97, "science": .85, "degree": .9, "research": .5, "births": .5,
                         "patients": .3, "public": .2, "screen": .4, "microbes": .7, "genes": .5},
        "phlebotomist": {"patients": .9, "hands": .9, "degree": .1, "long_training": .02,
                         "lab": .5, "high_pay": .15, "surgery": .2},
      },
    },
    "mental health & counseling": {
      "a": {"mental_health": .95, "patients": .85, "nine2five": .7, "uniform": .05,
            "hands": .05, "emergency": .1, "shifts": .15, "speaking": .3, "physical": .03},
      "leaves": {
        "clinical psychologist": {"degree": .95, "long_training": .8, "research": .3, "high_pay": .6},
        "counselor / therapist": {"degree": .6, "long_training": .3, "self_emp": .5, "high_pay": .4},
        "addiction counselor": {"addiction": .95, "degree": .5, "serious_ill": .5, "government": .4},
      },
    },
    "veterinary care": {
      "a": {"animals": .98, "living": .97, "patients": .9, "public": .8,
            "uniform": .8, "healthcare": .6, "hands": .8, "children": .02},
      "leaves": {
        "veterinarian": {"degree": .97, "long_training": .9, "surgery": .7, "prescribe": .9, "high_pay": .6, "manage": .5},
        "veterinary nurse / technician": {"degree": .3, "surgery": .3, "high_pay": .25, "care_daily": .5},
      },
    },
    "care work": {
      "a": {"care_daily": .95, "people_core": .95, "degree": .08, "long_training": .02,
            "high_pay": .1, "physical": .7, "shifts": .7, "uniform": .5, "patients": .6,
            "hands": .7, "science": .05, "prescribe": .01},
      "leaves": {
        "caregiver / home health aide": {"travel": .4, "nine2five": .3},
        "care home worker": {"nine2five": .2, "shifts": .9, "serious_ill": .3},
      },
    },
  },
},

# =========================================================================
"engineering": {
  "a": {"engineer_id": .93, "degree": .85, "screen": .65, "design": .7,
        "numbers": .7, "adv_math": .5, "science": .55, "high_pay": .7,
        "office": .55, "nine2five": .75, "indoors": .7, "clients_biz": .75,
        "public": .12, "make_physical": .45, "data_info": .35, "tools": .3,
        "hands": .2, "shifts": .12, "research": .3, "people_core": .05},
  "fields": {
    "mechanical & industrial engineering": {
      "a": {"tools": .4, "factory": .3, "engines": .25},
      "leaves": {
        "mechanical engineer": {"fix_repair": .2, "machines_op": .1},
        "automotive engineer": {"vehicles": .95, "engines": .6, "factory": .5},
        "robotics engineer": {"hardware": .85, "code": .7, "software": .5, "engines": .3},
        "HVAC engineer": {"buildings": .8, "pipes": .75, "energy": .75, "travel": .5, "fix_repair": .4},
        "manufacturing / industrial engineer": {"factory": .9, "manage": .45, "engines": .1},
      },
    },
    "aerospace engineering": {
      "a": {"aircraft": .97, "vehicles": .8, "adv_math": .7, "high_pay": .8,
            "government": .35, "science": .65, "lab": .25},
      "leaves": {
        "aerospace engineer": {},
        "propulsion engineer": {"engines": .97, "energy": .6, "danger": .2, "lab": .4},
        "avionics engineer": {"hardware": .9, "code": .5, "software": .4, "electric_wire": .5},
        "flight test engineer": {"travel": .5, "danger": .35, "data_info": .6, "indoors": .5,
                                 "machines_op": .2, "test_qa": .8},
        "spacecraft / satellite engineer": {"government": .5, "code": .45, "research": .5},
      },
    },
    "civil & structural engineering": {
      "a": {"buildings": .95, "indoors": .55, "travel": .45, "government": .3, "uniform": .3, "danger": .15},
      "leaves": {
        "civil engineer": {},
        "structural engineer": {"adv_math": .7, "design": .9, "indoors": .7},
        "transportation engineer": {"vehicles": .75, "government": .5, "rail": .3},
        "geotechnical engineer": {"earth_env": .85, "rocks": .8, "lab": .3, "indoors": .45},
        "land surveyor": {"indoors": .2, "tools": .75, "engineer_id": .3, "degree": .5, "design": .2,
                          "screen": .4, "property": .3, "hands": .4},
      },
    },
    "electrical & electronics engineering": {
      "a": {"electric_wire": .7, "hardware": .8, "energy": .3},
      "leaves": {
        "electrical engineer": {"energy": .7, "buildings": .3},
        "electronics engineer": {"hardware": .95, "factory": .3, "lab": .3},
        "power systems engineer": {"energy": .95, "buildings": .4, "travel": .4},
        "telecommunications engineer": {"comms_net": .95, "hardware": .7, "software": .4,
                                        "travel": .45, "buildings": .3},
        "semiconductor / chip design engineer": {"lab": .5, "factory": .5, "hardware": .97,
                                                 "adv_math": .65, "code": .5, "high_pay": .85},
        "embedded systems engineer": {"code": .9, "software": .7, "hardware": .9, "screen": .85},
      },
    },
    "chemical, materials & resources engineering": {
      "a": {"lab": .45, "science": .8, "factory": .35, "danger": .25},
      "leaves": {
        "chemical engineer": {"chemicals": .95, "factory": .6, "energy": .35, "lab": .7},
        "materials engineer": {"lab": .7, "research": .5, "chemicals": .5},
        "petroleum engineer": {"mining": .9, "energy": .9, "rocks": .6, "travel": .6, "indoors": .4,
                               "danger": .4, "high_pay": .9},
        "mining engineer": {"mining": .95, "rocks": .8, "danger": .5, "indoors": .35,
                            "earth_env": .5, "machines_op": .2},
        "nuclear engineer": {"energy": .95, "danger": .4, "government": .5, "science": .85},
      },
    },
    "bio & environmental engineering": {
      "a": {},
      "leaves": {
        "biomedical engineer": {"healthcare": .7, "living": .7, "hardware": .7, "lab": .5},
        "environmental engineer": {"earth_env": .9, "pollution": .85, "indoors": .5, "government": .4},
        "agricultural engineer": {"crops": .6, "animals": .3, "indoors": .4, "machines_op": .2, "earth_env": .4},
      },
    },
    "marine engineering": {
      "a": {"ships": .97, "vehicles": .7},
      "leaves": {
        "naval architect": {"design": .95},
        "marine engineer": {"engines": .7, "fix_repair": .4, "travel": .4, "indoors": .5},
      },
    },
  },
},

# =========================================================================
"software & information technology": {
  "a": {"screen": .97, "software": .85, "code": .6, "office": .6, "indoors": .97,
        "degree": .6, "high_pay": .8, "nine2five": .7, "data_info": .8,
        "clients_biz": .7, "public": .1, "design": .5, "numbers": .4,
        "hands": .05, "make_physical": .05, "adv_math": .3, "people_core": .05,
        "uniform": .02, "physical": .02, "self_emp": .25, "creative": .3},
  "fields": {
    "software development": {
      "a": {"code": .95},
      "leaves": {
        "software engineer / developer": {},
        "frontend developer": {"visual": .7, "design": .7},
        "mobile app developer": {"mobile": .95, "visual": .4},
        "game developer": {"games": .97, "visual": .5, "creative": .5},
        "machine learning engineer": {"ml_ai": .95, "data_work": .5, "adv_math": .8,
                                      "research": .4, "science": .4},
        "blockchain developer": {"crypto": .95, "finance_ind": .5, "money_others": .2, "adv_math": .5},
      },
    },
    "data & analytics": {
      "a": {"numbers": .8, "adv_math": .6, "research": .35, "data_work": .85},
      "leaves": {
        "data scientist": {"adv_math": .85, "code": .85, "science": .4, "ml_ai": .7},
        "data analyst": {"code": .4, "adv_math": .5, "writing": .3, "speaking": .3, "data_work": .95},
        "data engineer": {"code": .9, "adv_math": .4, "ml_ai": .1},
        "database administrator": {"code": .6, "fix_repair": .3, "shifts": .3, "servers": .6},
      },
    },
    "infrastructure & operations": {
      "a": {"fix_repair": .4, "shifts": .3, "code": .5, "servers": .85},
      "leaves": {
        "devops / site reliability engineer": {"code": .8, "emergency": .3, "engineer_id": .6},
        "system administrator": {"code": .3, "hardware": .5, "servers": .95},
        "network engineer": {"hardware": .5, "engineer_id": .6, "comms_net": .85},
        "cloud architect": {"design": .85, "high_pay": .9, "manage": .3, "servers": .7,
                            "degree": .8, "fix_repair": .1},
        "IT support technician": {"public": .6, "people_core": .4, "hardware": .5, "code": .1,
                                  "high_pay": .3, "degree": .3, "fix_repair": .7, "servers": .6},
      },
    },
    "cybersecurity": {
      "a": {"cyber": .95, "protect": .6, "code": .5},
      "leaves": {
        "cybersecurity analyst": {"emergency": .3, "shifts": .3},
        "penetration tester (ethical hacker)": {"code": .8, "self_emp": .3, "travel": .3},
      },
    },
    "product & quality": {
      "a": {"code": .2},
      "leaves": {
        "product manager (tech)": {"manage": .6, "speaking": .6, "writing": .5, "design": .4, "market_promo": .3},
        "UX / UI designer": {"visual": .9, "design": .95, "creative": .7, "code": .15, "drawing": .3},
        "QA / software tester": {"code": .4, "writing": .3, "test_qa": .95},
        "technical writer": {"writing": .95, "content": .5, "code": .1},
      },
    },
  },
},

# =========================================================================
"science & research": {
  "a": {"science": .95, "research": .9, "degree": .95, "long_training": .8,
        "data_info": .6, "screen": .6, "writing": .6, "adv_math": .5,
        "lab": .5, "public": .1, "people_core": .05, "high_pay": .55,
        "nine2five": .7, "office": .4, "government": .4, "teach_higher": .3,
        "speaking": .3, "clients_biz": .4, "uniform": .2, "indoors": .8},
  "fields": {
    "physical sciences": {
      "a": {"adv_math": .7},
      "leaves": {
        "physicist": {"adv_math": .9},
        "astronomer": {"screen": .8, "shifts": .4, "earth_env": .2, "lab": .3, "aircraft": .2},
        "chemist": {"lab": .9, "danger": .2, "chemicals": .95},
        "materials scientist": {"lab": .85, "factory": .2, "chemicals": .6},
      },
    },
    "life sciences": {
      "a": {"living": .9, "lab": .7},
      "leaves": {
        "biologist": {},
        "microbiologist": {"lab": .95, "healthcare": .3, "microbes": .95},
        "geneticist": {"lab": .9, "healthcare": .3, "adv_math": .5, "genes": .95, "microbes": .5},
        "biochemist": {"lab": .95, "chemicals": .7, "microbes": .6},
        "marine biologist": {"ships": .5, "water": .8, "earth_env": .7, "indoors": .4,
                             "animals": .6, "travel": .4},
        "ecologist": {"earth_env": .9, "pollution": .7, "indoors": .35, "animals": .4,
                      "plants": .5, "travel": .4, "lab": .3},
        "zoologist": {"animals": .95, "indoors": .4, "travel": .4},
        "botanist": {"plants": .95, "indoors": .5, "earth_env": .5, "animals": .05},
      },
    },
    "earth & environment": {
      "a": {"earth_env": .95, "indoors": .45, "travel": .4, "lab": .35},
      "leaves": {
        "geologist": {"rocks": .95, "mining": .5, "tools": .4},
        "meteorologist": {"screen": .85, "indoors": .8, "news_media": .3, "perform": .2, "shifts": .4},
        "oceanographer": {"ships": .6, "water": .9, "travel": .5},
        "environmental scientist": {"pollution": .9, "government": .5, "writing": .5},
        "volcanologist / seismologist": {"rocks": .8, "danger": .25, "travel": .5},
      },
    },
    "social & formal sciences": {
      "a": {"lab": .05, "office": .6, "adv_math": .3},
      "leaves": {
        "mathematician": {"adv_math": .98, "numbers": .9},
        "statistician": {"adv_math": .95, "numbers": .95, "code": .5, "data_work": .8},
        "economist": {"numbers": .9, "adv_math": .7, "finance_ind": .7, "politics": .5, "government": .5},
        "archaeologist": {"hist_culture": .95, "indoors": .35, "travel": .6, "hands": .5, "tools": .4},
        "historian": {"hist_culture": .95, "writing": .8, "teach_higher": .4},
        "linguist": {"language_dom": .95, "writing": .6},
        "political scientist": {"politics": .9, "writing": .7, "government": .4},
      },
    },
    "academia & research support": {
      "a": {},
      "leaves": {
        "university professor": {"teach": .9, "teach_higher": .97, "speaking": .8, "writing": .8, "lab": .3},
        "research lab technician": {"lab": .9, "degree": .6, "long_training": .2, "hands": .6,
                                    "research": .5, "writing": .2, "high_pay": .35, "teach_higher": .05},
        "clinical research associate": {"healthcare": .85, "living": .8, "serious_ill": .4,
                                        "travel": .5, "writing": .6, "lab": .3, "patients": .3},
      },
    },
  },
},

# =========================================================================
"education": {
  "a": {"teach": .95, "people_core": .8, "speaking": .8, "public": .7,
        "indoors": .9, "degree": .75, "nine2five": .8, "government": .5,
        "children": .5, "screen": .4, "writing": .4, "data_info": .4,
        "high_pay": .35, "shifts": .08, "uniform": .03, "creative": .3,
        "hands": .1, "clients_biz": .1, "office": .2},
  "fields": {
    "school teaching": {
      "a": {"children": .9},
      "leaves": {
        "primary school teacher": {"children": .97},
        "secondary school teacher": {"children": .8, "degree": .85},
        "kindergarten / preschool teacher": {"children": .98, "young_kids": .95, "degree": .4,
                                             "care_daily": .5, "physical": .4, "high_pay": .2},
        "special education teacher": {"disabilities": .95, "care_daily": .7, "mental_health": .3},
        "school principal": {"manage": .95, "teach": .4, "office": .6, "high_pay": .6},
        "teaching assistant": {"degree": .3, "high_pay": .1, "manage": .02},
      },
    },
    "specialist instruction": {
      "a": {"children": .35, "government": .2, "self_emp": .45},
      "leaves": {
        "private tutor": {"nine2five": .3, "self_emp": .8, "children": .6},
        "language teacher": {"language_dom": .9, "travel": .3},
        "music teacher": {"music_dom": .95, "creative": .6, "perform": .3},
        "driving instructor": {"driving": .95, "vehicles": .7, "machines_op": .5, "degree": .05, "indoors": .1},
        "corporate trainer": {"clients_biz": .8, "children": .02, "travel": .5, "office": .5, "high_pay": .5},
        "yoga / fitness instructor": {"fit_sport": .95, "physical": .8, "children": .1, "degree": .15,
                                      "uniform": .3, "nine2five": .3, "shifts": .4},
      },
    },
    "education support": {
      "a": {"teach": .3, "children": .4},
      "leaves": {
        "librarian": {"data_info": .8, "writing": .3, "speaking": .2, "public": .8, "hist_culture": .3, "children": .3},
        "school counselor": {"mental_health": .8, "people_core": .9, "children": .8},
        "curriculum developer": {"writing": .8, "office": .6, "screen": .8, "speaking": .3, "children": .2},
      },
    },
  },
},

# =========================================================================
"law, government & public safety": {
  "a": {"government": .6, "enforce": .5, "data_info": .5, "indoors": .6,
        "public": .6, "high_pay": .5, "uniform": .4, "protect": .4,
        "legal": .4, "nine2five": .5, "people_core": .4, "writing": .4,
        "make_physical": .02, "sales": .01, "creative": .02},
  "fields": {
    "legal profession": {
      "a": {"legal": .97, "degree": .9, "writing": .8, "office": .8, "screen": .8,
            "uniform": .1, "government": .3, "high_pay": .75, "long_training": .7,
            "enforce": .3, "clients_biz": .5, "nine2five": .6, "protect": .2},
      "leaves": {
        "lawyer / attorney": {"courtroom": .7, "speaking": .6},
        "judge": {"courtroom": .97, "government": .95, "high_pay": .9, "manage": .5, "long_training": .9},
        "prosecutor": {"courtroom": .9, "government": .95, "enforce": .7},
        "corporate counsel": {"clients_biz": .95, "courtroom": .2, "nine2five": .8},
        "paralegal": {"degree": .5, "long_training": .1, "high_pay": .35, "courtroom": .3, "speaking": .1},
        "notary": {"public": .8, "nine2five": .8, "courtroom": .05, "self_emp": .5},
      },
    },
    "police & security": {
      "a": {"uniform": .9, "protect": .9, "enforce": .9, "danger": .6, "physical": .6,
            "shifts": .8, "nine2five": .2, "emergency": .7, "government": .8,
            "degree": .25, "driving": .5, "screen": .25, "office": .2, "hands": .3},
      "leaves": {
        "police officer": {"driving": .8, "emergency": .9, "danger": .85},
        "detective / criminal investigator": {"uniform": .3, "data_info": .6, "screen": .5,
                                              "writing": .5, "emergency": .4},
        "prison officer": {"driving": .1, "indoors": .9, "emergency": .5},
        "security guard": {"government": .15, "degree": .05, "high_pay": .15, "enforce": .6, "emergency": .4, "danger": .4},
        "bodyguard": {"government": .1, "travel": .7, "high_pay": .5, "danger": .7, "public": .3},
        "border / customs officer": {"travel": .1, "data_info": .5, "driving": .2, "danger": .4},
        "private investigator": {"government": .05, "uniform": .05, "self_emp": .8, "data_info": .7,
                                 "screen": .5, "driving": .6, "emergency": .1},
      },
    },
    "fire & rescue": {
      "a": {"emergency": .98, "uniform": .98, "danger": .9, "physical": .9,
            "shifts": .9, "nine2five": .1, "government": .9, "protect": .95,
            "tools": .7, "degree": .1, "hands": .7, "driving": .5, "enforce": .3},
      "leaves": {
        "firefighter": {},
        "search & rescue / lifeguard": {"fit_sport": .5, "water": .7, "ships": .3, "earth_env": .4, "tools": .4},
      },
    },
    "military": {
      "a": {"military": .98, "government": .98, "uniform": .99, "danger": .7,
            "physical": .8, "shifts": .8, "nine2five": .15, "travel": .6,
            "protect": .9, "enforce": .5, "tools": .6, "degree": .3, "emergency": .5},
      "leaves": {
        "soldier (army)": {"hands": .5},
        "military officer": {"manage": .9, "degree": .7, "high_pay": .55, "speaking": .4},
        "navy sailor": {"ships": .95, "vehicles": .4},
        "air force pilot": {"aircraft": .97, "driving": .8, "machines_op": .8, "vehicles": .8,
                            "degree": .7, "high_pay": .6},
      },
    },
    "civil service & politics": {
      "a": {"government": .95, "office": .7, "screen": .7, "nine2five": .8,
            "uniform": .05, "enforce": .3, "danger": .03, "writing": .6, "data_info": .7,
            "physical": .03, "protect": .1, "emergency": .02},
      "leaves": {
        "civil servant / public administrator": {"degree": .75, "legal": .5, "high_pay": .5,
                                                 "manage": .4, "politics": .3},
        "diplomat": {"travel": .8, "politics": .7, "speaking": .6, "language_dom": .5, "high_pay": .6,
                     "degree": .85},
        "politician": {"politics": .98, "speaking": .9, "perform": .4, "public": .9, "travel": .6,
                       "high_pay": .6, "manage": .6, "nine2five": .2},
        "urban planner": {"buildings": .8, "design": .6, "degree": .8},
        "tax inspector": {"numbers": .9, "finance_ind": .5, "enforce": .7, "legal": .5},
        "intelligence officer": {"data_info": .85, "protect": .75, "degree": .8, "travel": .45,
                                 "danger": .35, "politics": .35, "cyber": .35, "language_dom": .35,
                                 "research": .65, "high_pay": .6},
        "postal worker": {"driving": .6, "physical": .6, "public": .7, "office": .1, "screen": .05,
                          "writing": .02, "degree": .03, "data_info": .2, "uniform": .8, "travel": .3},
      },
    },
  },
},

# =========================================================================
"business, finance & management": {
  "a": {"office": .85, "screen": .85, "data_info": .8, "indoors": .97,
        "nine2five": .8, "degree": .7, "high_pay": .6, "numbers": .6,
        "clients_biz": .7, "writing": .4, "people_core": .2, "manage": .3,
        "make_physical": .01, "uniform": .04, "physical": .01, "hands": .02,
        "speaking": .3, "public": .3},
  "fields": {
    "accounting & audit": {
      "a": {"numbers": .95, "finance_ind": .5, "legal": .25},
      "leaves": {
        "accountant": {"taxes": .4},
        "auditor": {"travel": .4, "enforce": .6, "clients_biz": .9, "test_qa": .4},
        "tax consultant": {"taxes": .95, "legal": .5, "public": .5, "self_emp": .4},
        "bookkeeper": {"degree": .3, "high_pay": .3, "clients_biz": .6, "long_training": .05, "payroll": .3},
        "payroll administrator": {"payroll": .95, "degree": .3, "high_pay": .35},
      },
    },
    "banking & investment": {
      "a": {"finance_ind": .95, "numbers": .9, "money_others": .8, "high_pay": .75},
      "leaves": {
        "investment banker": {"high_pay": .97, "nine2five": .2, "shifts": .5, "adv_math": .5,
                              "manage": .4, "trading": .4},
        "stock trader": {"trading": .95, "high_pay": .9, "adv_math": .5, "shifts": .3,
                         "screen": .95, "clients_biz": .5},
        "financial analyst": {"writing": .5, "adv_math": .5, "data_work": .5, "trading": .1},
        "financial advisor / wealth manager": {"public": .8, "people_core": .6, "sales": .5,
                                               "clients_biz": .3, "insurance": .2},
        "bank teller": {"public": .95, "degree": .2, "high_pay": .2, "money_others": .5,
                        "sales": .3, "people_core": .5, "long_training": .02, "loans": .3},
        "loan officer": {"loans": .95, "public": .7, "property": .3, "sales": .4},
        "actuary": {"adv_math": .97, "insurance": .8, "data_work": .7, "long_training": .6,
                    "high_pay": .9, "public": .05, "money_others": .4},
        "insurance underwriter": {"insurance": .97, "legal": .3, "money_others": .4, "public": .1},
        "insurance claims adjuster": {"insurance": .97, "public": .6, "travel": .4, "legal": .4,
                                      "driving": .3, "money_others": .3},
      },
    },
    "management & administration": {
      "a": {"manage": .6, "speaking": .5},
      "leaves": {
        "chief executive (CEO / director)": {"manage": .98, "high_pay": .95, "speaking": .8, "travel": .5,
                                             "nine2five": .4, "market_promo": .3, "money_others": .3},
        "operations manager": {"manage": .9, "projects_temp": .1},
        "project manager": {"manage": .8, "writing": .5, "projects_temp": .9},
        "human resources manager": {"hiring": .95, "people_core": .8, "manage": .8, "legal": .3,
                                    "writing": .5, "numbers": .3},
        "management consultant": {"travel": .6, "clients_biz": .97, "speaking": .7, "high_pay": .85,
                                  "writing": .6, "nine2five": .5, "manage": .3, "projects_temp": .7},
        "entrepreneur / startup founder": {"self_emp": .97, "manage": .8, "market_promo": .6, "sales": .5,
                                           "nine2five": .2, "high_pay": .5, "speaking": .6},
        "office administrator": {"manage": .2, "degree": .35, "high_pay": .25, "people_core": .3},
        "executive assistant": {"manage": .05, "people_core": .8, "degree": .4, "high_pay": .4,
                                "writing": .5, "travel": .3},
        "recruiter": {"hiring": .95, "people_core": .8, "public": .85, "sales": .5,
                      "speaking": .5, "manage": .05},
        "supply chain manager": {"shipping": .9, "numbers": .7, "travel": .4, "factory": .3, "manage": .7},
      },
    },
  },
},

# =========================================================================
"sales, marketing & customer service": {
  "a": {"public": .75, "sales": .6, "indoors": .9, "people_core": .5,
        "market_promo": .4, "screen": .5, "high_pay": .35, "degree": .35,
        "nine2five": .55, "speaking": .4, "data_info": .4, "office": .4,
        "make_physical": .02, "uniform": .2, "creative": .1, "numbers": .35},
  "fields": {
    "marketing & advertising": {
      "a": {"market_promo": .95, "sales": .3, "office": .7, "screen": .85, "degree": .6,
            "clients_biz": .6, "creative": .5, "writing": .5, "content": .5, "public": .3},
      "leaves": {
        "marketing manager": {"manage": .8, "speaking": .6, "high_pay": .6},
        "digital marketing specialist": {"numbers": .6, "content": .7, "seo_web": .5, "manage": .05},
        "SEO specialist": {"seo_web": .95, "numbers": .5, "code": .2, "writing": .6, "content": .3},
        "social media manager": {"content": .9, "visual": .4, "shifts": .3},
        "advertising creative / copywriter": {"creative": .85, "writing": .9, "visual": .4},
        "public relations specialist": {"news_media": .7, "writing": .7, "speaking": .6},
        "market research analyst": {"numbers": .8, "data_work": .6, "adv_math": .4, "research": .7,
                                    "writing": .5, "creative": .1},
      },
    },
    "sales": {
      "a": {"sales": .95},
      "leaves": {
        "B2B sales representative": {"clients_biz": .95, "travel": .7, "speaking": .5, "high_pay": .6,
                                     "office": .65, "screen": .65, "driving": .3, "uniform": .05},
        "retail sales assistant / cashier": {"degree": .08, "uniform": .5, "physical": .35, "shifts": .7,
                                             "high_pay": .1, "nine2five": .3, "long_training": .02},
        "real estate agent": {"property": .97, "driving": .7, "self_emp": .6, "indoors": .6,
                              "legal": .4, "high_pay": .5, "shifts": .5, "nine2five": .3},
        "car salesperson": {"vehicles": .95, "driving": .4, "uniform": .2, "high_pay": .4},
        "telemarketer": {"screen": .7, "degree": .05, "high_pay": .08, "shifts": .3,
                         "speaking": .3, "office": .7, "public": .8},
        "pharmaceutical sales rep": {"healthcare": .5, "travel": .7, "clients_biz": .9, "driving": .6, "high_pay": .6},
      },
    },
    "customer service": {
      "a": {"sales": .15, "people_core": .7, "degree": .15, "high_pay": .15},
      "leaves": {
        "customer service / call center agent": {"screen": .75, "shifts": .5, "office": .7,
                                                 "public": .9, "uniform": .05},
      },
    },
  },
},

# =========================================================================
"arts, media & entertainment": {
  "a": {"creative": .8, "content": .6, "self_emp": .5, "nine2five": .3,
        "degree": .35, "high_pay": .3, "shifts": .5, "indoors": .7,
        "government": .05, "uniform": .03, "data_info": .3, "public": .4,
        "make_physical": .2, "people_core": .15, "clients_biz": .35, "enforce": .01},
  "fields": {
    "visual arts & design": {
      "a": {"visual": .9, "design": .6, "screen": .6},
      "leaves": {
        "graphic designer": {"screen": .95, "design": .95, "clients_biz": .6, "drawing": .4},
        "illustrator": {"hands": .5, "content": .7, "drawing": .95},
        "photographer": {"photos": .97, "tools": .6, "travel": .5, "indoors": .4, "public": .6, "hands": .4},
        "fine artist / painter": {"hands": .8, "drawing": .7, "make_physical": .6, "screen": .1, "self_emp": .9},
        "animator": {"screen": .95, "video_anim": .9, "drawing": .7, "film_stage": .4, "games": .3},
        "video editor": {"screen": .95, "video_anim": .95, "drawing": .05, "film_stage": .5,
                         "content": .8, "tools": .05, "hands": .05, "travel": .1},
        "interior designer": {"buildings": .8, "public": .6, "travel": .4, "property": .4},
        "fashion designer": {"fashion": .97, "sew": .6, "drawing": .5, "make_physical": .4, "hands": .5},
        "industrial / product designer": {"make_physical": .6, "engineer_id": .2, "clients_biz": .7, "degree": .6},
        "tattoo artist": {"hands": .95, "drawing": .85, "public": .9, "people_core": .6, "screen": .1,
                          "beauty": .4, "self_emp": .7, "make_physical": .3},
        "architect": {"buildings": .95, "degree": .95, "long_training": .8, "design": .98,
                      "screen": .85, "high_pay": .6, "office": .7, "clients_biz": .6,
                      "nine2five": .7, "self_emp": .3, "legal": .2},
      },
    },
    "performing arts": {
      "a": {"perform": .9, "public": .5, "travel": .4, "shifts": .8, "nine2five": .1, "visual": .1},
      "leaves": {
        "actor": {"film_stage": .9},
        "musician / singer": {"music_dom": .97, "hands": .6, "content": .7},
        "DJ": {"music_dom": .9, "hospitality": .6, "alcohol": .3, "tools": .6, "shifts": .95},
        "dancer": {"physical": .9, "fit_sport": .3, "music_dom": .4},
        "comedian": {"writing": .5, "content": .6, "speaking": .8},
        "film / theater director": {"film_stage": .95, "video_anim": .6, "manage": .8,
                                    "perform": .2, "high_pay": .5},
        "orchestra conductor": {"music_dom": .97, "manage": .7, "degree": .6, "long_training": .8},
        "magician / circus performer": {"hands": .7, "travel": .6, "danger": .2},
      },
    },
    "writing & journalism": {
      "a": {"writing": .9, "content": .8, "screen": .8, "perform": .05, "visual": .1},
      "leaves": {
        "journalist / reporter": {"news_media": .95, "travel": .5, "public": .6, "shifts": .5, "degree": .6},
        "news anchor / TV presenter": {"news_media": .95, "perform": .9, "film_stage": .5, "high_pay": .5, "beauty": .2},
        "editor (publishing)": {"news_media": .5, "nine2five": .7, "office": .6, "manage": .4},
        "author / novelist": {"self_emp": .9, "nine2five": .4, "public": .1, "creative": .9},
        "screenwriter": {"film_stage": .8, "self_emp": .7, "creative": .9},
        "translator / interpreter": {"language_dom": .97, "creative": .2, "self_emp": .6, "travel": .3, "content": .3},
      },
    },
    "digital media & broadcasting": {
      "a": {"content": .9, "screen": .7},
      "leaves": {
        "podcast host": {"perform": .7, "speaking": .8, "music_dom": .1, "news_media": .3, "self_emp": .7},
        "youtuber / influencer": {"perform": .8, "visual": .6, "video_anim": .6, "market_promo": .5,
                                  "self_emp": .9, "film_stage": .2},
        "radio host": {"perform": .8, "news_media": .6, "music_dom": .4, "shifts": .6},
        "streamer (gaming)": {"games": .9, "perform": .8, "self_emp": .9, "shifts": .6},
        "sound engineer": {"music_dom": .9, "tools": .7, "hardware": .7, "film_stage": .5,
                           "creative": .5, "content": .3, "hands": .3, "screen": .75,
                           "indoors": .9, "shifts": .7, "public": .3, "perform": .03},
        "camera operator": {"film_stage": .7, "video_anim": .8, "photos": .3, "tools": .8,
                            "visual": .8, "news_media": .4, "travel": .5, "hands": .6,
                            "content": .5, "screen": .3, "physical": .4},
        "game designer": {"games": .97, "design": .8, "writing": .4, "screen": .9, "self_emp": .2},
      },
    },
    "culture & heritage": {
      "a": {"hist_culture": .9, "creative": .3, "self_emp": .1, "nine2five": .8, "degree": .7},
      "leaves": {
        "museum curator": {"content": .3, "research": .5, "manage": .4, "writing": .5},
        "art conservator / restorer": {"hands": .8, "make_physical": .4, "lab": .3, "fix_repair": .6,
                                       "chemicals": .4, "drawing": .3, "screen": .2},
        "auctioneer / antiques dealer": {"sales": .8, "public": .8, "speaking": .6, "self_emp": .6},
      },
    },
  },
},

# =========================================================================
"sports & fitness": {
  "a": {"fit_sport": .96, "physical": .85, "nine2five": .25, "shifts": .6,
        "public": .6, "uniform": .5, "degree": .2, "indoors": .5,
        "people_core": .5, "high_pay": .3, "travel": .4, "data_info": .1,
        "screen": .1, "make_physical": .02, "office": .05},
  "fields": {
    "athletes & competitors": {
      "a": {"perform": .8, "danger": .3, "travel": .7, "teach": .05},
      "leaves": {
        "professional footballer / soccer player": {"high_pay": .7, "children": .02},
        "professional athlete (other sports)": {"high_pay": .5},
        "esports player": {"games": .95, "screen": .95, "physical": .1, "indoors": .95, "danger": .02},
        "racing driver": {"driving": .95, "vehicles": .9, "machines_op": .8, "danger": .8, "engines": .4},
      },
    },
    "coaching & instruction": {
      "a": {"teach": .85, "speaking": .5},
      "leaves": {
        "sports coach": {"children": .4, "manage": .5},
        "personal trainer": {"people_core": .9, "self_emp": .7, "indoors": .8},
        "ski / snowboard instructor": {"indoors": .05, "danger": .4, "travel": .6, "earth_env": .3, "shifts": .5},
        "swimming instructor": {"water": .95, "children": .6, "indoors": .7, "danger": .2},
        "mountain / climbing guide": {"indoors": .02, "danger": .7, "travel": .7, "earth_env": .6, "protect": .4},
        "referee / umpire": {"enforce": .9, "teach": .1, "perform": .3, "travel": .5, "people_core": .2},
      },
    },
  },
},

# =========================================================================
"hospitality, food & tourism": {
  "a": {"hospitality": .9, "public": .8, "shifts": .8, "nine2five": .15,
        "uniform": .7, "degree": .1, "high_pay": .15, "physical": .6,
        "indoors": .85, "people_core": .6, "hands": .5, "data_info": .05,
        "screen": .1, "office": .03, "make_physical": .1, "long_training": .05},
  "fields": {
    "kitchen & food preparation": {
      "a": {"food_domain": .97, "cook": .9, "hands": .9, "make_physical": .5,
            "public": .3, "creative": .4, "danger": .2, "tools": .5},
      "leaves": {
        "head chef": {"manage": .8, "creative": .7, "high_pay": .4, "long_training": .3},
        "line cook": {"manage": .05, "creative": .2},
        "pastry chef / baker": {"nine2five": .2, "shifts": .9, "creative": .6, "make_physical": .7},
        "butcher": {"animals": .3, "danger": .3, "public": .8, "sales": .7, "creative": .05, "cook": .4},
        "sommelier (wine expert)": {"alcohol": .95, "cook": .2, "public": .9, "sales": .5, "teach": .3,
                                    "high_pay": .4, "speaking": .4, "hands": .2, "creative": .2},
      },
    },
    "food & drink service": {
      "a": {"food_domain": .9, "sales": .3, "cook": .3},
      "leaves": {
        "waiter / server": {"physical": .7, "cook": .05, "alcohol": .3},
        "barista": {"cook": .8, "creative": .3},
        "bartender": {"alcohol": .95, "cook": .6, "shifts": .95, "creative": .3, "speaking": .2},
        "restaurant manager": {"manage": .9, "high_pay": .3, "numbers": .4, "cook": .1},
        "food delivery rider": {"driving": .9, "indoors": .05, "vehicles": .4, "public": .5,
                                "uniform": .6, "danger": .3, "cook": .01, "people_core": .2},
      },
    },
    "hotels & accommodation": {
      "a": {"food_domain": .2, "buildings": .1},
      "leaves": {
        "hotel manager": {"manage": .9, "high_pay": .4, "office": .3, "numbers": .4, "nine2five": .3,
                          "events_org": .3},
        "hotel receptionist": {"screen": .6, "nine2five": .2, "physical": .2, "speaking": .2, "language_dom": .2},
        "housekeeper / room attendant": {"clean": .95, "physical": .8, "public": .2, "care_daily": .2, "hands": .8},
        "concierge": {"people_core": .9, "physical": .1, "public": .95, "speaking": .3,
                      "travel": .05, "language_dom": .2, "events_org": .2},
      },
    },
    "travel & tourism": {
      "a": {"travel": .6, "speaking": .4, "language_dom": .2},
      "leaves": {
        "tour guide": {"hist_culture": .5, "speaking": .8, "indoors": .3, "physical": .5, "teach": .3},
        "travel agent": {"screen": .7, "office": .6, "sales": .5, "indoors": .95, "travel": .3, "nine2five": .7},
        "flight attendant": {"aircraft": .95, "uniform": .97, "travel": .95, "shifts": .95,
                             "emergency": .4, "protect": .3, "vehicles": .5},
        "cruise ship staff": {"ships": .95, "water": .7, "travel": .9, "shifts": .9},
        "event / wedding planner": {"events_org": .97, "manage": .5, "creative": .4, "travel": .3,
                                    "self_emp": .5, "nine2five": .3, "clients_biz": .3,
                                    "food_domain": .2, "projects_temp": .6},
      },
    },
  },
},

# =========================================================================
"transport & logistics": {
  "a": {"vehicles": .6, "driving": .6, "machines_op": .5, "uniform": .6,
        "shifts": .7, "nine2five": .3, "degree": .1, "indoors": .3,
        "physical": .5, "travel": .5, "public": .4, "data_info": .1,
        "screen": .1, "office": .05, "people_core": .2, "high_pay": .3,
        "hands": .4, "danger": .3, "make_physical": .02},
  "fields": {
    "aviation": {
      "a": {"aircraft": .95, "travel": .7, "danger": .3, "degree": .4, "high_pay": .6},
      "leaves": {
        "airline pilot": {"machines_op": .9, "driving": .85, "high_pay": .9, "long_training": .6,
                          "uniform": .97, "manage": .5, "shifts": .95},
        "helicopter pilot": {"machines_op": .9, "driving": .85, "emergency": .4, "danger": .5},
        "air traffic controller": {"screen": .9, "indoors": .95, "driving": .02, "machines_op": .05,
                                   "speaking": .5, "high_pay": .8, "shifts": .9, "protect": .6,
                                   "emergency": .5, "physical": .05, "travel": .1, "hands": .02},
        "drone operator": {"machines_op": .7, "driving": .2, "visual": .4, "screen": .5,
                           "uniform": .2, "self_emp": .4, "travel": .5},
        "aircraft mechanic": {"fix_repair": .95, "engines": .8, "hands": .9, "tools": .95,
                              "driving": .05, "machines_op": .2, "indoors": .7, "physical": .7},
      },
    },
    "maritime": {
      "a": {"ships": .96, "water": .9, "indoors": .3, "earth_env": .3, "travel": .7},
      "leaves": {
        "ship captain": {"manage": .9, "machines_op": .7, "high_pay": .6, "long_training": .4},
        "sailor / deckhand": {"physical": .85, "hands": .7, "high_pay": .2, "danger": .5},
        "fisherman": {"animals": .6, "food_domain": .5, "physical": .9, "danger": .6,
                      "self_emp": .5, "uniform": .4, "make_physical": .2, "living": .4},
        "harbor pilot / port worker": {"machines_op": .6, "physical": .7, "shifts": .8, "shipping": .6},
      },
    },
    "road & rail": {
      "a": {},
      "leaves": {
        "truck driver (long haul)": {"machines_op": .9, "driving": .98, "shipping": .85,
                                     "travel": .8, "indoors": .1, "public": .1},
        "bus driver": {"machines_op": .9, "driving": .98, "public": .8, "travel": .2, "indoors": .1},
        "taxi / rideshare driver": {"driving": .98, "public": .9, "self_emp": .8, "uniform": .1,
                                    "machines_op": .5, "indoors": .2},
        "train driver": {"rail": .97, "machines_op": .95, "driving": .8, "public": .2, "indoors": .4},
        "delivery courier": {"driving": .9, "shipping": .9, "physical": .6, "public": .7,
                             "travel": .4, "indoors": .1, "machines_op": .3},
        "chauffeur": {"driving": .97, "public": .6, "people_core": .7, "uniform": .6,
                      "high_pay": .25, "indoors": .2, "machines_op": .1},
      },
    },
    "warehousing & logistics": {
      "a": {"driving": .2, "travel": .1, "indoors": .8, "vehicles": .2, "uniform": .6, "shipping": .7},
      "leaves": {
        "warehouse worker": {"physical": .9, "machines_op": .4, "hands": .6, "public": .05},
        "forklift operator": {"machines_op": .9, "physical": .5, "danger": .3, "public": .05},
        "crane operator": {"machines_op": .97, "danger": .5, "buildings": .6, "indoors": .1,
                           "high_pay": .4, "heights": .6, "shipping": .4},
        "logistics coordinator": {"screen": .8, "office": .7, "data_info": .6, "numbers": .5,
                                  "shipping": .95, "physical": .1, "machines_op": .02, "degree": .3,
                                  "nine2five": .7, "clients_biz": .7, "uniform": .1},
      },
    },
  },
},

# =========================================================================
"construction & skilled trades": {
  "a": {"make_physical": .9, "hands": .9, "tools": .9, "physical": .85,
        "buildings": .7, "indoors": .4, "uniform": .7, "danger": .5,
        "degree": .06, "screen": .05, "office": .03, "high_pay": .4,
        "nine2five": .6, "shifts": .2, "travel": .4, "fix_repair": .5,
        "self_emp": .4, "public": .4, "clients_biz": .4, "data_info": .03,
        "long_training": .2, "people_core": .1},
  "fields": {
    "construction site": {
      "a": {"buildings": .95},
      "leaves": {
        "construction laborer": {"danger": .7, "self_emp": .2, "fix_repair": .2, "high_pay": .25,
                                 "heights": .4, "stone_brick": .3, "long_training": .03},
        "carpenter": {"wood": .95, "fix_repair": .4, "creative": .2, "indoors": .5},
        "bricklayer / mason": {"stone_brick": .95, "fix_repair": .2, "indoors": .15},
        "roofer": {"heights": .95, "danger": .8, "indoors": .02, "fix_repair": .6},
        "scaffolder": {"heights": .95, "danger": .8, "indoors": .05, "fix_repair": .1, "make_physical": .5},
        "painter & decorator": {"danger": .3, "indoors": .7, "creative": .6, "fix_repair": .3},
        "tiler / flooring installer": {"indoors": .8, "danger": .2, "stone_brick": .4, "creative": .05},
        "glazier (glass installer)": {"glass": .95, "danger": .5, "fix_repair": .5, "heights": .4},
        "heavy equipment operator": {"machines_op": .95, "vehicles": .5, "driving": .6, "indoors": .05},
        "site manager / foreman": {"manage": .9, "screen": .3, "physical": .4, "high_pay": .55,
                                   "hands": .3, "office": .2, "writing": .3, "projects_temp": .5},
        "building inspector": {"enforce": .8, "test_qa": .5, "government": .6, "writing": .5, "screen": .4,
                               "physical": .3, "hands": .2, "make_physical": .1, "degree": .4, "legal": .3},
      },
    },
    "installation & maintenance trades": {
      "a": {"fix_repair": .8, "travel": .5, "public": .6, "buildings": .6, "indoors": .6},
      "leaves": {
        "electrician": {"electric_wire": .97, "danger": .6, "energy": .4},
        "plumber": {"pipes": .97, "water": .5, "danger": .3},
        "welder": {"metal": .95, "danger": .6, "factory": .4, "buildings": .4, "public": .1,
                   "tools": .97, "fix_repair": .4, "travel": .3, "creative": .03, "uniform": .9,
                   "stone_brick": .02, "wood": .02},
        "HVAC technician": {"pipes": .6, "energy": .7, "electric_wire": .6},
        "elevator technician": {"electric_wire": .7, "danger": .5, "machines_op": .2,
                                "high_pay": .55, "fix_repair": .9, "self_emp": .05},
        "locksmith": {"danger": .1, "protect": .6, "emergency": .3, "buildings": .3, "self_emp": .6},
        "solar panel installer": {"energy": .9, "electric_wire": .6, "heights": .7, "danger": .5,
                                  "indoors": .05, "earth_env": .3},
        "auto mechanic": {"vehicles": .95, "fix_repair": .97, "engines": .9, "buildings": .05,
                          "indoors": .7, "danger": .3, "travel": .1},
        "handyman": {"self_emp": .8, "fix_repair": .97, "public": .8, "travel": .6,
                     "pipes": .3, "electric_wire": .3, "wood": .5, "buildings": .5},
      },
    },
  },
},

# =========================================================================
"manufacturing & production": {
  "a": {"factory": .85, "make_physical": .9, "hands": .8, "indoors": .95,
        "uniform": .7, "physical": .6, "tools": .7, "degree": .1,
        "nine2five": .5, "shifts": .5, "high_pay": .3, "public": .1,
        "screen": .1, "office": .03, "data_info": .05, "machines_op": .4,
        "danger": .3, "clients_biz": .5, "people_core": .05},
  "fields": {
    "production line": {
      "a": {},
      "leaves": {
        "factory worker / assembler": {"machines_op": .5, "long_training": .02},
        "machinist / CNC operator": {"machines_op": .9, "metal": .8, "tools": .95, "screen": .3, "long_training": .2},
        "quality control inspector": {"test_qa": .9, "enforce": .5, "data_info": .3, "screen": .3,
                                      "machines_op": .1, "writing": .3, "physical": .3, "make_physical": .3},
        "production supervisor": {"manage": .9, "physical": .3, "high_pay": .45, "screen": .3},
        "food production worker": {"food_domain": .9, "cook": .3, "danger": .2},
      },
    },
    "craft & artisan work": {
      "a": {"factory": .2, "creative": .5, "self_emp": .6, "machines_op": .1,
            "danger": .1, "public": .4, "nine2five": .6, "shifts": .2},
      "leaves": {
        "tailor / seamstress": {"fashion": .9, "sew": .95, "hands": .95},
        "jeweler": {"precious": .95, "sales": .5, "high_pay": .4, "hands": .95, "beauty": .2, "fashion": .3},
        "watchmaker": {"fix_repair": .7, "hands": .97, "precious": .4, "hardware": .4, "fashion": .05,
                       "nine2five": .8, "danger": .02, "travel": .05, "protect": .02},
        "furniture maker / cabinetmaker": {"wood": .95, "buildings": .2, "tools": .9},
        "glassblower / ceramicist": {"glass": .9, "creative": .8, "danger": .3},
        "shoemaker / cobbler": {"fix_repair": .6, "fashion": .7, "sew": .4},
        "brewer / distiller": {"alcohol": .9, "food_domain": .9, "cook": .5, "science": .3,
                               "factory": .5, "creative": .4, "chemicals": .3},
        "3D printing technician": {"screen": .6, "design": .4, "hardware": .6, "factory": .4, "creative": .3},
      },
    },
  },
},

# =========================================================================
"agriculture, nature & animals": {
  "a": {"indoors": .1, "physical": .8, "living": .8, "earth_env": .6,
        "make_physical": .5, "hands": .8, "uniform": .3, "degree": .15,
        "nine2five": .3, "shifts": .6, "high_pay": .2, "self_emp": .5,
        "tools": .6, "public": .2, "screen": .05, "office": .02,
        "data_info": .03, "danger": .3, "machines_op": .3, "clients_biz": .3},
  "fields": {
    "farming": {
      "a": {"crops": .5, "animals": .4, "food_domain": .6, "driving": .5, "machines_op": .5},
      "leaves": {
        "crop farmer": {"crops": .95, "plants": .9, "animals": .1},
        "livestock farmer / rancher": {"animals": .95, "crops": .2},
        "dairy farmer": {"animals": .95, "food_domain": .8, "nine2five": .1, "shifts": .9},
        "winemaker / vineyard worker": {"crops": .9, "plants": .7, "alcohol": .8, "food_domain": .8,
                                        "cook": .2, "science": .3, "creative": .3},
        "beekeeper": {"animals": .9, "danger": .4, "food_domain": .7, "uniform": .8, "machines_op": .05},
        "agronomist / agricultural scientist": {"science": .8, "degree": .8, "research": .5, "screen": .4,
                                                "crops": .8, "plants": .85, "lab": .3, "high_pay": .4,
                                                "physical": .3},
      },
    },
    "forestry & land": {
      "a": {"crops": .3, "animals": .3, "earth_env": .9},
      "leaves": {
        "forester / logger": {"danger": .7, "machines_op": .5, "tools": .9, "wood": .5, "plants": .6},
        "park ranger": {"government": .8, "protect": .6, "enforce": .5, "teach": .3, "uniform": .9,
                        "animals": .5, "public": .6, "danger": .3, "pollution": .6},
        "gardener / landscaper": {"crops": .8, "plants": .9, "public": .5, "buildings": .2,
                                  "creative": .3, "design": .3},
        "florist": {"indoors": .8, "sales": .7, "creative": .7, "public": .8, "crops": .5, "plants": .9,
                    "physical": .4, "design": .4, "danger": .02, "machines_op": .02},
      },
    },
    "animal work": {
      "a": {"animals": .97, "crops": .05, "people_core": .3, "public": .5},
      "leaves": {
        "zookeeper": {"danger": .4, "teach": .2, "government": .3, "uniform": .8, "self_emp": .05},
        "animal trainer": {"teach": .5, "public": .6, "danger": .3, "fit_sport": .03},
        "dog groomer": {"beauty": .6, "hair": .4, "indoors": .8, "self_emp": .6, "danger": .1, "physical": .5},
        "pet sitter / dog walker": {"indoors": .3, "self_emp": .9, "care_daily": .4, "danger": .05, "physical": .5},
        "horse trainer / equestrian worker": {"danger": .5, "fit_sport": .6, "teach": .4},
        "animal shelter worker": {"care_daily": .5, "indoors": .7, "public": .6, "high_pay": .08,
                                  "government": .2, "self_emp": .05, "uniform": .5},
      },
    },
  },
},

# =========================================================================
"personal & community services": {
  "a": {"people_core": .8, "public": .8, "indoors": .85, "degree": .15,
        "high_pay": .2, "hands": .5, "self_emp": .4, "nine2five": .5,
        "data_info": .1, "screen": .1, "office": .05, "make_physical": .05,
        "uniform": .3, "physical": .4, "clients_biz": .1},
  "fields": {
    "beauty & grooming": {
      "a": {"beauty": .95, "hands": .95, "creative": .5, "shifts": .4, "nine2five": .4,
            "sales": .3, "physical": .5, "long_training": .05},
      "leaves": {
        "hairdresser / barber": {"hair": .97, "self_emp": .6},
        "beautician / cosmetologist": {"nails_skin": .9, "hair": .4, "self_emp": .5,
                                       "fashion": .3, "travel": .05},
        "nail technician": {"nails_skin": .9, "hair": .02, "self_emp": .5, "physical": .2},
        "makeup artist": {"nails_skin": .6, "fashion": .5, "film_stage": .3, "travel": .6,
                          "self_emp": .7, "visual": .3},
        "massage therapist": {"spine_joints": .6, "beauty": .2, "healthcare": .6, "patients": .5,
                              "care_daily": .2, "physical": .7, "self_emp": .6, "creative": .1},
      },
    },
    "home & facility services": {
      "a": {"hands": .7, "physical": .7, "self_emp": .3, "creative": .02, "people_core": .3},
      "leaves": {
        "cleaner / janitor": {"clean": .97, "uniform": .6, "shifts": .5, "public": .2, "travel": .1,
                              "long_training": .01, "animals": .01},
        "window cleaner": {"clean": .9, "heights": .7, "glass": .3, "danger": .5, "indoors": .05,
                           "buildings": .3, "self_emp": .6},
        "pest control technician": {"animals": .6, "chemicals": .6, "danger": .3, "travel": .6,
                                    "driving": .5, "uniform": .8, "science": .2},
        "chimney sweep": {"heights": .6, "buildings": .4, "danger": .4, "travel": .6,
                          "self_emp": .7, "fix_repair": .3},
      },
    },
    "community & social work": {
      "a": {"government": .5, "mental_health": .3, "care_daily": .3, "hands": .1,
            "degree": .5, "writing": .3, "speaking": .3, "physical": .1},
      "leaves": {
        "social worker": {"degree": .8, "children": .4, "travel": .4, "legal": .3, "mental_health": .5,
                          "disabilities": .3},
        "childcare worker / nanny": {"children": .98, "young_kids": .8, "care_daily": .8, "government": .1,
                                     "degree": .15, "physical": .5, "cook": .3, "self_emp": .5},
        "youth worker": {"children": .8, "young_kids": .1, "care_daily": .1, "teach": .4, "fit_sport": .2},
        "life coach": {"self_emp": .9, "speaking": .6, "mental_health": .6, "government": .02, "screen": .4},
        "funeral director / mortician": {"death": .97, "government": .05, "manage": .5, "serious_ill": .3,
                                         "uniform": .5, "nine2five": .3, "shifts": .5,
                                         "mental_health": .2, "hands": .4},
      },
    },
    "religious & spiritual": {
      "a": {"religion": .97, "speaking": .7, "people_core": .9, "mental_health": .4,
            "government": .05, "self_emp": .1, "writing": .4, "teach": .4,
            "hands": .05, "physical": .05, "shifts": .5, "high_pay": .1},
      "leaves": {
        "priest / pastor / clergy": {"perform": .3, "children": .2, "death": .3},
        "monk / nun": {"public": .3, "speaking": .3, "indoors": .8, "nine2five": .2},
        "astrologer / fortune teller": {"religion": .5, "self_emp": .9, "public": .9, "content": .3},
      },
    },
  },
},

}


def compile():
    """Flatten the taxonomy into (questions, careers).

    questions: qid -> {"text", "default"}
    careers:   name -> {"path": [sector, field], "profile": {qid: p_yes}}
    """
    questions = {qid: {"text": text, "default": default}
                 for qid, (default, text) in QUESTIONS.items()}
    careers = {}
    for sector, s in T.items():
        s_attrs = s.get("a", {})
        for field, f in s["fields"].items():
            f_attrs = f.get("a", {})
            for leaf, l_attrs in f["leaves"].items():
                profile = {}
                profile.update(s_attrs)
                profile.update(f_attrs)
                profile.update(l_attrs)
                for qid in profile:
                    if qid not in questions:
                        raise KeyError(f"unknown question id {qid!r} in {leaf!r}")
                careers[leaf] = {"path": [sector, field], "profile": profile}
    return questions, careers


if __name__ == "__main__":
    qs, cs = compile()
    sectors = {}
    for c in cs.values():
        sectors[c["path"][0]] = sectors.get(c["path"][0], 0) + 1
    print(f"{len(qs)} questions, {len(cs)} occupations across {len(sectors)} sectors:")
    for name, n in sorted(sectors.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3d}  {name}")
