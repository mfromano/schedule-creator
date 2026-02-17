Schedule Creation Guide

# Overview

Residents take their schedules seriously. Some dissatisfaction is inevitable. You may face undue, inappropriate pressure to make a schedule that benefits select interests. You have to rise above it and basically ignore everyone. You do not answer to anyone but the program director. Do not delete the schedules from previous years. Your successors may find this information useful. 

# Graduation Requirements

| Breast | 12 weeks AND 300 cases throughout residency (ask Sandria for BreastTrak records) |
| --- | --- |
| NucMed (Non NR-DR) | 16 weeksNote: 4 week Mai, Mch, Peds, or Mx = 1 week Mnuc equivalent |
| NucMed (NR-DR) | 48 weeks (R4 research counts towards this requirement),4 weeks each of Mai, Mch, Mb, and Mucic (completed by default, anytime during residency)Note: the 4:1 week Mai/Mch/Peds/Mx:Mnuc equivalence factor does NOT apply to NR-DR |
| ESIR | 12 weeksCurrent scheme: R1=none; R2 = Vir/Sir (2), R3 = Zir/Mir (2), R4= Mir x8 (8) |
| ESNR | 6 blocks neuro in R4 (max 1 on Smr) |
| T32 | Typical Breast, non-NRDR NucMed reqs |

# Planning for the new year

## Simplified rotation scheduling

As of 2025, the current “Master Spreadsheet.xlsm” file is updated to deal with dozens of policy/rotation changes incurred since its creation 10 years ago. It doesn’t automatically generate the schedule, but it does simplify information gathering/auditing/planning. The downside to automation is fragility. Please do not change formulas unless you know what you are doing. Even something as inconsequential as renaming a tab will cause some functions to fail.

## Setting up the academic year

The following logic is baked into the spreadsheet formulae and should be automatically generated.

| If july 1 is a | NF starts | Block 1 duration | Block 2-12 duration | Block 13 duration |
| --- | --- | --- | --- | --- |
| Mon | Last Sunday in June | 4 weeks | 4 weeks | Whatever gets to june 30th (4 wk ± few days) |
| Tues/Wed | Last Sunday in June | A few days LESS than 4 weeks |
| Thurs/Fri | First Sunday in July | A few days MORE than 4 weeks |
| Sat/Sun | First Sunday in July | 4 weeks |

## The master file

The prior year’s rotation chief should have prepared a new “Schedule Creation (20XX-20YY).xlsm” file for you. A few do’s and don'ts:

*   If confronted with a dialog box warning you about the presence of macros, click “Enable Macros.”
    
*   If asked to update links to external sources, click “Update.”
    
*   Do NOT select any option that says Delete columns/rows. This will destroy the excel. Instead, right click and click “Clear Contents”
    
*   Do NOT Cut and paste any content. This will destroy the excel. Instead, copy and paste the content, and then clear contents in the original location.
    

## File architecture overview

| Tab Name | Description | Handle |
| --- | --- | --- |
| Overview | Input parameters, specific notes/todo’s for next year’s chief |  |
| Key | List of rotations, which PGY they apply to |  |
| Historical | Resident roster, memory buffer of past 4 years’ assignments. Needs updating at EOY, with any schedule change |  |
| Transfers | List of transfer residents, credited rotation times in unit of weeks |  |
| Historical Tabulation | Audit of rotation/section times per resident, analysis by quartile | LOCK |
| R1-R2 Tracks | Rotation track generators |  |
| Preferences | Manual entry of resident preferences |  |
| No Call Prefs | Internal reference tool: calendarized no-call preference days referenced in Base Schedule, Night Float tabs | LOCK/HIDE |
| Base Schedule | Backbone schedule creation |  |
| NF recs | Calculation of NF shifts assignment per class in upcoming year | LOCK |
| Night Float | Assign nightfloat shifts |  |
| Current Year Tabulation | Audit of rotation/section times per resident, accounting for upcoming year assignments | LOCK |
| Publish | Template page to create publishable spreadsheet | DON’T EDIT |

  

## Updating the roster

Occasionally there are transfer residents added in the middle of the year:

1.  In the “Historical” tab, add incoming residents’ name(s) to column C, maintaining alphabetical order and format (Last name, First name). This is also where you remove residents who drop out, and revise which residents are doing subspecialty pathways (ESIR/ESNR/T32/NRDR).
    
2.  In the “Transfers” tab, add a row and update numbers for Xnuc, Xm, Xir, and Xp columns to designate weeks spent on nuclear medicine, mammography, IR, and pediatrics rotations at their outside institution. This will have already been done for residents that transferred in previous years.
    

Updating Core Rotations & Tracks

1.  “Key” spreadsheet: Add/remove any rotations to match policies for the academic year. Data validation rules help keep Section/Label keys consistent for downstream formulas.
    
2.  No resident can be assigned to two different hospital systems (e.g., UCSF, SFGH, VA) in the same block as it creates problems for payroll.
    
3.  “R1/R2 Tracks” spreadsheets: Follow the steps delineated in the tabs. 
    

1.  Grid sequence lengths should equal the number of residents in the class. If grid sequence length < # residents, there will be duplicate schedules; if grid sequence length > # residents, there will be excess “missed” rotations. This logic is built into the file.
    
2.  Identify critical core rotations (Mc, Sir) that cannot be missed by any resident. These will require manually editing the auto-generated tracks to contain an occasional block with doubled residents. These residents must be pulled from another service; the easiest are Mai,Mch,Peds,Mb. Do not pull from Mnuc or Pcbi given impact on graduation requirement.
    
3.  Try to intermix “hard” and “easy” rotations. You know which ones these are.
    
4.  For R1 tracks, they typically get 0.5 blocks Mnuc, Pcbi
    
5.  For R2 tracks, they typically get 0.5 blocks Mnuc, Peds
    
6.  For R2 tracks, the # months between Sx blocks should be ~6 months for adequate spacing/recovery. A Mnf week is assigned sometime between those blocks.
    
7.  The R2 tracks are shared at the time of request solicitation. It’s okay if changes need to happen, but it’ll save you some emails if you make sure everything looks good before sharing. 
    

5.  R3 and R4 residents don’t have “tracks.” You make their schedule manually.
    

  

# Resident requests

## Auditing Resident Rotation Times

Before soliciting preference requests, your first order of business is to audit residents’ history in terms of rotation times. The “Historical Tabulation” tab breaks down residents’ exposure across all major sections, ignoring vacation, sick, academic days. The unit of time is weeks. Superimposed colors indicate intraclass quartile (green: >75%tile; gray: >50%tile; yellow: <50%tile; red: <25%tile). Standard deviations are narrow in R1-2 years and broaden with seniority. The graduating R4 class (your class) is included as a safety check to simply ensure graduation requirements are met. Use this information to identify sections which residents are falling short on and rectify these deficiencies. This is baked into the logic of R2 track rankings and the “R3-4 Recs” tab, as described below.

## Important Dates & People

Take note of AIRP session dates, CORE dates, and number of residents applying T32/NRDR/ESIR/ESNR. You will reference this information many times down the road.

## Rotation Request Form

The latest version of the survey form combines general rotation, vacation, academic day, and call preferences, and is unified across all resident classes. Feel free to separate them once again if desired. In reality, none of the requests need to be solicited or granted. Feel free to remove questions and be careful about over-promising. For sanity, prioritize multiple choice responses (forcing functions) over free-text entries. 

  

Go through the survey and update major dates. Some survey links also need to be updated with tables created by the “Schedule Creation.xlsm” file:

*   “R2 Tracklist” tab: Copy columns BK:CA (step 4) into a discrete excel file which you’ll share
    
*   “Historical Tabulation” tab: Copy columns B, BJ, and BK into a discrete excel file. Feel free to split into separate R2, R3, and R4 sheets.
    

  

Aim to send this by mid February, with requests due in mid March.

## Research/CEP

E-mail current R3s to solicit research and CEP proposals.  Do this by mid January. Stipulations are:

*   Maximum of 2 months research/CEP allowed per resident unless they have supplementary funding. 
    
*   T32 residents cannot apply
    
*   ESIR and NR-DR residents: one month research applies towards ESIR/NRDR graduation requirements  
      
    

Once aggregated, prepare a summary of proposals and review them with Soonmee. Only assign electives once core clinical staffing needs are met (~45 residents/day). Giving too many electives will be disastrous for clinical operations.

## NR/DR

Maintain a very guarded stance if asked about the feasibility of allowing >2 residents/class to pursue NR/DR. They are siphoned to nuclear medicine for 6 blocks/year/person for two consecutive years, creating a large vacancy the remaining co-residents must fill. A single extra person will make your life difficult, their co-residents spread thin, and sections perpetually near minimum staffing. To a lesser extent, the same goes for ESIR, ESNR, and T32, but it would only impact a single year.

## Preference Entry

The default excel sheet generated by google forms is pretty monstrous. Resist the temptation to look at entries before the deadline. If you are savvy, filter and search functions can save you a lot of time organizing the data. 

One important nuance is that “no-call weekends” should include the date range of Fri->Mon; the schedule file ignores weekends, so NF assignments beginning on a “no-call” Sunday would fall undetected unless you included the subsequent Monday.

  

After manually cleaning the request form preferences, manually import them into the “Preferences” tab. The most important is the “No Call, Vac, Acad, Leave” column (AA), where the format should be strictly comma-separated MM/DD. Feel free to use chatgpt. The spreadsheet integrates this info into subsequent tabs for easier visualization.

# Schedule Creation

## The “Historical” and “Base Schedule” tabs

Graduation requirements are based on the 4-year sum of rotation assignments as penciled into the “base schedule.” This tabulation ignores vacation, sick, academic days, and night float assignments. This is why we keep a “Base Schedule” tab isolated from night float assignments.

  

The “Base Schedule” tab is what you use to create the backbone for the schedule. This tab is also organized to help you identify staffing needs as you fill it out. Rows 101-151 should ideally be green after you’ve finished scheduling all residents rotations (but before you start assigning NF).

  

## Schedule the R1s and R2s

Start with R1 and R2 schedules as they are track-based with minimal, if any, need for customization. 

1.  For R1’s, it’s completely up to you who gets what track. You can somewhat game the system by prioritizing residents who have Msampler preferences for sections with trainee shortage. Leave these blocks labeled as the generic “Msampler” for now. We will address this at the end.
    
2.  For R2’s, it’s helpful to visualize track rank data as a matrix of tracks \* # people per rank order:
    

|  | No. people ranking as #1 | No. people ranking as #2 | No. people ranking as #3 |
| --- | --- | --- | --- |
| Track 1 | 1 | 0 | 0 |
| Track 2 | 0 | 2 | 0 |
| Track 3 | 4 | 2 | 1 |

1.  Identify tracks that very few people ranked high, assign those (in above example, assign Track 1 to the single person who ranked it highly)
    
2.  Identify tracks that many people ranked high, resort to their 2nd,3rd, etc choices (ie. track 3 above)
    
3.  Make sure exclusion criteria are upheld based on info from “Historical Tabulation” tab, and if the resident marked interest in a subspecialization pathway.
    
4.  Try to limit assignments within 1-3rd choices. Not always possible.
    

3.  Enter these assigned tracks into the “Base Schedule” tab
    

## Schedule the R3s

As with the first and second years, please note that no resident can be assigned to two different hospital systems (e.g., Moffitt/Zion, SFGH, VA) in the same block as it creates problems for payroll.

1.  Identify AIRP, Learning Center, and CORE dates, these will be the toughest blocks to schedule around.
    
2.  Assign AIRP, with max of 3-4 residents per session.
    
3.  Make sure LC is assigned to all rising R3s in the last full rotation block before the Core exam.
    
4.  If a resident did IR over Christmas/New Year’s in the previous academic year, do not make them do Zir over the holidays again. Don't assign an R3 to Zir in the block before LC. They don't like it. Give it to an R4 who asks for IR.
    
5.  NRDR should complete breast requirements by EOY; T32, ESIR, ESNR residents should complete NM/breast requirements by EOY. Not always possible.
    
6.  Each resident will now miss three rotations instead of just one (the “leftover rotation” as well as the rotations that would have occurred during Learning Center and AIRP).
    

1.  The “R3-4 Recs” tab gives some recommendations regarding how many blocks of a given section to assign a resident. It is based on their rotation deficiencies, preferred rotations, and subspecialty pathways (if any). Feel free to use it as a guideline.
    

8.  Enter each R3 residents schedule into the “Base Schedule” tab.
    

  

## Schedule the R4s

1.  For each month, create a list of rotations that still need to be staffed.
    
2.  The “R3-4 Recs” tab gives some recommendations regarding how many blocks of a given section to assign a resident. It is based on their rotation deficiencies, preferred rotations, and subspecialty pathways (if any). Feel free to use it as a guideline.
    
3.  All residents get Mx block unless T32 OR less than 3 blocks left after fulfilling grad reqs (NRDR+ESNR pathway). Unfilled Mx months=lucky people get double Mx
    
4.  Assign FSEs in the first half of the year to half of the fourth years, and in the second half of the year to the other half of the fourth years. Breast FSE requires 6 months without exception.
    
5.  Things can get tricky during the Learning Center month unless there is some diversity of FSEs. Your bottom line is ensuring staffing, so you’ll need to convince people to make compromises if necessary.
    
6.  For any resident that does not have sufficient breast for graduation, assign Pcbi rotations.
    
7.  For any resident that does not have sufficient nuclear medicine for graduation, assign Mnuc rotations as needed. Alternatively, if only a small number of nuclear medicine credit-weeks is needed, you can assign residents to Mp, Mch, Mai, or Mx, since each of these four-week rotations is credited as one week of nuclear medicine. (Of note, Mc, Mmr, and Zai do not give one week of nuclear medicine credit.)
    
8.  Assign all approved research, clinical educator project, and clinical elective months. Avoid assigning these months during times of staffing hardship (e.g., Learning Center, RSNA).
    
9.  Identify any rising fourth year residents that have done only one month of pediatrics and assign them to Peds. If possible make sure everyone will have completed 3 months of MSK (Vb, Mb, and Ser in some combination) by the end of residency.  Per Soonmee, the only hard-and-fast rules are the mammo and nucs requirements, but it seems like it has generally been thought that 2 blocks of peds and 3 total blocks of some type of MSK are recommended (Soonmee didn’t seem to feel strongly about this though). 
    
10.  Consider pulling a T32 resident to help cover clinical services in times of extreme need (usually Learning Center). This should only be done as a last resort, as residents’ research time should be respected. T32 residents can never be pulled for more than two months, but ideally should not be pulled for more than two weeks.
    
11.  Enter each R4 residents schedule into the “Base Schedule” tab.
    

## Assign Night Float

The rotation chief assigns NF weeks (Snf, Snf2, Mnf) since they impact daytime staffing. Use the “NF recs” tab to review the census data. Determine in advance which residents should get a particular permutation of shifts. Enter Mnf, Snf, and Snf2 weeks into the “Night Float” tab of the scheduling spreadsheet. Red cells indicate weeks in which the resident has requested vacation/no call. Remaining cells are color coded to reflect section staffing. Similarly, rows 104-118 keep a running tally of staffing after NF has been assigned.

  

Some nuances:

| Shift | Applies to | Notes/Special periods |
| --- | --- | --- |
| Snf | R2 | Prepackaged into track options |
| Mnf | R2, R3 | R2: 2 weeks by defaultR3: 1-2 weeks (# Snf2 + # Mnf = 3 MAX)Block 1: only assign R3 (can make longer to ease R2 integration)LC/CORE: only assign R2 |
| Snf2 | R3, R4 | R3: 1-2 weeks (# Snf2 + # Mnf = 3 MAX)R4: 2 weeks by defaultLC/CORE: only assign R4Post-CORE: only assign R3 |
| Sx | R2 | Prepackaged into track options |
| Mx | R4 | Cannot give Mx to T32 or residents doing 2+ subspecialization pathways (ie. ESNR+NRDR). Unfilled months= some lucky R4s get double Mx. Be judicious about who gets it. Preferably whoever had a poor R2 schedule. |

  

The easiest approach is working backwards from high constraint conditions: 

1.  Assign NF during LC+Core: R2 Mnf, R4 Snf2
    
2.  Assign NF during post-core period: R2-3 Mnf, Snf2
    
3.  Assign block 1 Mnf to R3
    
4.  Assign NF during AIRP periods
    
5.  Assign NF to remaining weeks of year
    
6.  Keep T32 unassigned until very end because they are most flexible
    
7.  Try to space out minimum 4 weeks between NFs
    

  

Some additional pointers:

*   Snf junior night float is easily added as two weeks to whomever is assigned Sx on a given month.
    
*   Try to pull from Pcmb, Mb, Mucic, Peds, Mnuc.
    
*   Be aware of the following conference dates when assigning night float to R3s: UCSF Annual review and Core Physics review courses
    
*   The R1 on Msampler should always be filling in for an upper level resident going on night float (which is why you should be pulling residents from rotations that the sampler can do)
    

## Assigning Sampler Rotation

1.  Go to the “Base Schedule” tab.
    
2.  In place of “Msampler,” you will now fill in specific rotations on Pcbi (1 week), Mucic OR Mir depending on preference (1 week), and Mnuc (two weeks), with the order to be determined by the night float schedule (i.e., the sampler resident should always be filling in for a resident on night float).
    

## Verifying Results

1.  Open the “Current Year Tabulation” tab. Confirm that all seniors will meet their graduation requirements by the end of the year.
    
2.  Confirm that all juniors that plan to do a T32 have met all their graduation requirements in the same way that you did for seniors. Though not absolutely mandatory, this should be a high priority.
    
3.  Open the “Night Float” tab and scroll down to row 106-118. Confirm that each service has an appropriate number of residents assigned each week. There is both a minimum and a maximum number of residents that can be assigned to any given service, and individual weeks will be highlighted if staffing falls below the minimum or above the maximum.
    

# Distributing the Schedule

## To the Residents

1.  Open the Master Schedule.
    
2.  Click on Tools > Macro > Macros.
    
3.  Select “Schedule\_Publish” and click “Run.”
    
4.  After some time, a new worksheet will be generated. Save this worksheet as “Resident Vacation Schedule 20XX-20XX”, editing the years applicable.
    
5.  Take a very close look at blocks 1, 13, as well as any blocks containing/flanking AIRP and CORE. The automation process glitches when task assignments are not cleanly occupying the standard bimonthly recipe.
    
6.  Upload the Schedule.xlsx file to Google Drive
    
7.  In top left menu, click “File > Save as Google Sheets”
    
8.  Open that file and edit Sharing privileges to “Anyone with the link”
    
9.  E-mail the link to all first through third years, as well as the incoming first years. Standard communication templates are in the google drive.
    
10.  Unless you’ve made a mistake, stick to the standard schedule and resist rotation trades. Trading rotations has a ripple effect that throws the schedule out of balance in ways that are difficult to immediately appreciate. If absolutely necessary, consider only “vertical trades” (i.e., along the same column), but even this will throw off some of the multi-year logic that is built into the system.
    
11.  Expect some complaints about the schedule. Do not take these complaints personally.
    
12.  Once satisfied that there are no glaring errors, let the call and vacation chiefs know they can begin their end of things.
    

## To Leadership and Administrators

E-mail the same google sheet to the program director, program coordinator, and all faculty.  Standard communication templates are in the google drive.

## Setting up the Master Spreadsheet for next year’s rotation chief

It used to be the case that the new rotation chief set up their own files. However, it honestly makes most sense for the seasoned rotation chief to just do this since they have presumably spent an inordinate amount of time looking at the file and are much more facile in setting things up.

  

1.  Locate the “Schedule Creation.xlsm” file you have been working on since at least March.
    
2.  Duplicate the file and rename it to match the year (e.g., “Schedule Creation 2026-2027.xlsm”). 
    
3.  Perform next steps on a workstation with a lot of processing power. It’ll be slow on an old laptop.
    
4.  Update the data for the new year. This must be done in a very specific way as described below, else you will break thousands of formulas that automate the rest of the spreadsheet.
    

1.  Select the tab labeled “Historical.”
    
2.  Select cells BG3 through HF200; click Edit > Copy.
    
3.  Select cell G3; click Edit > Paste Special > Values only.
    
4.  Select cells FG3 through HF200; Right-click > Clear Contents
    
5.  Identify the row corresponding to the first R3 resident. Lets call it row X. Select rows X through 200; click Edit > Copy (yes, include the empty cells). 
    
6.  Select cell A3; click Edit > Paste Special > Values only
    
7.  In Column B, add in the names of all incoming R1 (“LastName, FirstName”, alphabetical)
    
8.  In Column A, update PGY for everyone.
    
9.  Select “Base Schedule” tab, select cells D6 through BC100; click Edit > Copy.
    
10.  Return to “Historical” tab, select cell FG3 and click Edit > Paste Special > Values only
    

6.  Remove all manually entered data for prior year
    

1.  “Preferences” tab: select cells R3 through AA200; Right-click > “Clear Contents.”
    
2.  “Base Schedule” tab: select cells D6 through BC100; Right-click > “Clear Contents.”
    
3.  “Night Float” tab: select cell F103; click Edit > Copy. Select F7 through BE103; Edit > Paste Special > Formulas.
    

# Making Changes

Unless absolutely necessary to avoid a complete meltdown, avoid making any big changes and stick rigorously to the standardized curriculum.

# Miscellaneous Loose Ends

1.  The rotation request forms contain the information needed to update resident profiles on the department website ([http://www.radiology.ucsf.edu/education/residency-programs/diagnostic/residents](http://www.radiology.ucsf.edu/education/residency-programs/diagnostic/residents)). Please send this information to Sandria Wong and ask her to update the page in late June or early July; she will either do it herself or forward the information along to one of the IT staff.
    
2.  Update this guide if things have changed. It’s your final task as rotation chief!