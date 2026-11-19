"""Plain-language explanations from exact Python outputs, available without an LLM."""
from datetime import date
def money(value):
    return ("−" if value<0 else "")+f"₹{abs(value):,.0f}"


def explain_calendar(result):
    request = result["request"]
    gross, net = request["gross"], result["offer_net"]
    waiting, accepting = result["wait"]["expected"], result["accept"]["expected"]
    remainder = accepting-net
    difference = result["difference"]
    threshold = result["break_even_gross"]
    action = ("Accepting has the higher expected return" if difference>0 else
              "Keeping the dates available has the higher expected return" if difference<0 else
              "Both choices have the same expected return")
    evidence = result["evidence"]
    start = date.fromisoformat(request["start_date"]).strftime("%d %b %Y")
    end = date.fromisoformat(request["end_date"]).strftime("%d %b %Y")
    return [
        f"**What AdPlay keeps.** For {result['face']} from {start} to {end}, "
        f"the {money(gross)} media-rent offer contributes **{money(net)}** after the revenue share, commission, absorbed costs, selected lighting and any enabled receipt-timing adjustment. "
        "The comparison assumes the client has confirmed the booking.",
        f"**What waiting is worth.** Keeping the dates available produces an estimated **{money(waiting)}** from future bookings through 31 December. "
        f"Accepting leaves an estimated **{money(remainder)}** on the remaining dates. Adding the current offer gives **{money(accepting)}** in total.",
        f"**The decision.** {action}, by **{money(abs(difference))}** on average. "
        f"The break-even gross media rent is **{money(threshold)}**. At that price, the offer covers the expected contribution displaced on its dates plus the campaign costs.",
        f"**The risk.** Waiting produces no additional booking in **{result['wait']['probability_zero']:.0%}** of the simulated outcomes. "
        f"The middle 80% of waiting outcomes ranges from **{money(result['wait']['p10'])} to {money(result['wait']['p90'])}**. "
        "A campaign needs all its consecutive dates, so occupying even part of the festive window can prevent a longer booking.",
        f"**What supports the estimate.** The rate-and-duration samples include {evidence['local_bookings']} accepted bookings at this site "
        f"and {evidence['pooled_bookings']} across the portfolio. Local samples contribute about {evidence['local_weight']:.0%} of the mix. "
        "These are illustrative synthetic forecasts. The outcome range excludes uncertainty in the learned model parameters.",
    ]
