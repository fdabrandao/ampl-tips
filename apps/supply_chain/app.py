import streamlit as st
from amplpy import AMPL
import pandas as pd
import os
import re


class InputData:
    DEMAND_COLUMNS = ["Product", "Location", "Period", "Quantity", "DemandType"]
    STARTING_INVENTORY_COLUMNS = ["Product", "Location", "Period", "Quantity"]
    RATE_COLUMNS = ["Product", "Resource", "Rate", "Location", "Details"]
    AVAILABLE_CAPACITY_COLUMNS = ["Resource", "Location", "TotalCapacity", "Unit"]
    TRANSPORTATION_COSTS_COLUMNS = ["FromLocation", "ToLocation", "Allowed?", "Cost"]

    def __init__(self, xlsx_fname):
        self.dfs = pd.read_excel(
            xlsx_fname,
            sheet_name=None,
        )
        self.dfs["Demand"]["Period"] = pd.to_datetime(self.dfs["Demand"]["Period"])
        self.dfs["StartingInventory"]["Period"] = pd.to_datetime(
            self.dfs["StartingInventory"]["Period"]
        )

        def load_sheet(name, columns):
            if set(columns) - set(self.dfs[name].columns) != set():
                st.error(f"{name} sheet needs columns: {columns}")
                st.stop()
            return self.dfs[name][columns].copy()

        # Data
        self.demand = load_sheet("Demand", self.DEMAND_COLUMNS)
        self.starting_inventory = load_sheet(
            "StartingInventory", self.STARTING_INVENTORY_COLUMNS
        )
        self.rate = load_sheet("Rate", self.RATE_COLUMNS)
        self.available_capacity = load_sheet(
            "AvailableCapacity", self.AVAILABLE_CAPACITY_COLUMNS
        )
        self.transportation_costs = load_sheet(
            "TransportationCosts", self.TRANSPORTATION_COSTS_COLUMNS
        )

        # Dimensions
        self.all_products = list(sorted(set(self.demand["Product"])))
        self.all_components = ["Flour", "Sugar", "Chocolate"]
        self.all_locations = list(sorted(set(self.demand["Location"])))
        self.all_customers = ["Supermarket", "Restaurant", "Bulk"]
        self.all_resources = list(
            sorted(set([pair.split("_")[0] for pair in self.rate["Resource"]]))
        )
        self.all_resources_at = {l: set() for l in self.all_locations}
        for pair in self.rate["Resource"]:
            resource, location = pair.split("_")
            self.all_resources_at[location].add(resource)
        for location in self.all_resources_at:
            self.all_resources_at[location] = list(
                sorted(self.all_resources_at[location])
            )
        self.all_periods = list(
            sorted(set(self.demand["Period"]) | set(self.starting_inventory["Period"]))
        )
        self.all_suppliers = ["Flour Shop", "Chocolate Shop"]

    def filter_dimensions(self):
        cols = st.columns(3)
        with cols[0]:
            self.selected_products = st.multiselect(
                "Products:", self.all_products, default=self.all_products
            )
            # Filter products
            self.demand = self.demand[
                self.demand["Product"].isin(self.selected_products)
            ]
            self.starting_inventory = self.starting_inventory[
                self.starting_inventory["Product"].isin(self.selected_products)
            ]
            self.rate = self.rate[self.rate["Product"].isin(self.selected_products)]
        with cols[1]:
            self.selected_components = st.multiselect(
                "Components:", self.all_components, default=self.all_components
            )
            # FIXME: Nothing to filter yet
        with cols[2]:
            self.selected_locations = st.multiselect(
                "Locations:", self.all_locations, default=self.all_locations
            )
            # Filter locations
            self.demand = self.demand[
                self.demand["Location"].isin(self.selected_locations)
            ]
            self.starting_inventory = self.starting_inventory[
                self.starting_inventory["Location"].isin(self.selected_locations)
            ]
            self.rate = self.rate[self.rate["Location"].isin(self.selected_locations)]
            self.available_capacity = self.available_capacity[
                self.available_capacity["Location"].isin(self.selected_locations)
            ]
            self.transportation_costs = self.transportation_costs[
                self.transportation_costs["ToLocation"].isin(self.selected_locations)
            ]

        self.selected_customers = st.multiselect(
            "Customers:", self.all_customers, default=self.all_customers
        )
        # FIXME: Nothing to filter yet

        self.selected_resources = st.multiselect(
            "Resources:", self.all_resources, default=self.all_resources
        )
        # FIXME: Nothing to filter yet

        cols = st.columns(len(self.all_locations))
        resources_at = {}
        for i, location in enumerate(self.selected_locations):
            with cols[i]:
                resources_at[location] = st.multiselect(
                    f"Resources at {location}:",
                    self.all_resources,
                    default=self.all_resources_at.get(location, []),
                )
        # Filter resources at each location
        pairs = [
            (resource, location)
            for location in resources_at
            for resource in resources_at[location]
        ]
        self.rate = self.rate[
            self.rate["Resource"].isin(
                [f"{resource}_{location}" for (resource, location) in pairs]
            )
        ]
        mask = self.available_capacity.apply(
            lambda row: (row["Resource"], row["Location"]) in pairs, axis=1
        )
        self.available_capacity = self.available_capacity[mask]

        date_range = (
            min(self.all_periods).to_pydatetime(),
            max(self.all_periods).to_pydatetime(),
        )
        self.selected_range = st.slider(
            "Periods:",
            min_value=date_range[0],
            max_value=date_range[1],
            value=(date_range[0], date_range[1]),
            format="YYYY-MM-DD",
        )
        # Filter periods
        self.demand = self.demand[
            (self.demand["Period"] >= self.selected_range[0])
            & (self.demand["Period"] <= self.selected_range[1])
        ]
        self.starting_inventory = self.starting_inventory[
            (self.starting_inventory["Period"] >= self.selected_range[0])
            & (self.starting_inventory["Period"] <= self.selected_range[1])
        ]

        self.selected_suppliers = st.multiselect(
            "Suppliers:", self.all_suppliers, default=self.all_suppliers
        )
        # FIXME: Nothing to filter yet

    def edit_data(self):
        def data_editor(df, columns):
            return st.data_editor(
                df,
                disabled=[c for c in df.columns if c not in columns],
                hide_index=True,
            )

        st.write("Demand:")
        self.demand = data_editor(self.demand, ["Quantity"])

        st.write("StartingInventory:")
        self.starting_inventory = data_editor(self.starting_inventory, ["Quantity"])

        st.write("Rate:")
        self.rate = data_editor(self.rate, ["Rate"])

        st.write("AvailableCapacity:")
        self.available_capacity = data_editor(
            self.available_capacity, ["TotalCapacity"]
        )

        st.write("TransportationCosts:")
        self.transportation_costs = data_editor(self.transportation_costs, ["Cost"])


def main():
    st.markdown(
        """
    # 📦 Supply Chain Optimization
    
    
    """
    )

    instance = InputData(
        os.path.join(os.path.dirname(__file__), "InputDataProductionSolver.xlsx")
    )

    with st.expander("Dimensions"):
        instance.filter_dimensions()

    with st.expander("Data"):
        instance.edit_data()

    model = r"""
        set Products;  # Set of products
        set Locations;  # Set of distribution or production locations
        set TimePeriods ordered;  # Ordered set of time periods for planning

        param Demand{p in Products, l in Locations, t in TimePeriods} >= 0 default 0;
                # Demand for each product at each location during each time period
                
        var UnmetDemand{p in Products, l in Locations, t in TimePeriods} >= 0;
                # Quantity of demand that is not met for a product at a location in a time period
        var MetDemand{p in Products, l in Locations, t in TimePeriods} >= 0;
                # Quantity of demand that is met for a product at a location in a time period

        param InitialInventory{p in Products, l in Locations} >= 0 default 0;
                # Initial inventory levels for each product at each location
        var StartingInventory{p in Products, l in Locations, t in TimePeriods} >= 0;
                # Inventory at the beginning of each time period
        var EndingInventory{p in Products, l in Locations, t in TimePeriods} >= 0;
                # Inventory at the end of each time period

        var Production{p in Products, l in Locations, t in TimePeriods} >= 0;
                # Production volume for each product at each location during each time period

        minimize TotalCost:
            sum {p in Products, l in Locations, t in TimePeriods}
                (10 * UnmetDemand[p, l, t] + 5 * EndingInventory[p, l, t]);
                # Objective function to minimize total costs associated with unmet demand and leftover inventory
    """

    demand_fulfillment = r"""
        s.t. DemandFulfillment{p in Products, l in Locations, t in TimePeriods}:
            Demand[p, l, t] = MetDemand[p, l, t] + UnmetDemand[p, l, t];
                # Ensure that all demand is accounted for either as met or unmet
    """

    inventory_balance = r"""         
        s.t. InventoryFlow{p in Products, l in Locations, t in TimePeriods}:
            StartingInventory[p, l, t] =
                if ord(t) > 1 then
                    EndingInventory[p, l, prev(t)]
                else
                    InitialInventory[p, l];
                # Define how inventory is carried over from one period to the next
    """

    stock_balance = r"""       
        s.t. StockBalance{p in Products, l in Locations, t in TimePeriods}:
            StartingInventory[p, l, t] + Production[p, l, t] - Demand[p, l, t] = EndingInventory[p, l, t];
                # Balance starting inventory and production against demand to determine ending inventory
    """

    st.code(model)

    demand = instance.demand[["Product", "Location", "Period", "Quantity"]].copy()
    starting_inventory = instance.starting_inventory[
        ["Product", "Location", "Quantity"]
    ].copy()
    demand["Period"] = demand["Period"].dt.strftime("%Y-%m-%d")
    periods = list(sorted(set(demand["Period"])))
    demand.set_index(["Product", "Location", "Period"], inplace=True)
    starting_inventory.set_index(["Product", "Location"], inplace=True)

    ampl = AMPL()
    ampl.eval(model)
    ampl.set["Products"] = instance.selected_products
    ampl.set["Locations"] = instance.selected_locations
    ampl.set["TimePeriods"] = periods
    ampl.param["Demand"] = demand["Quantity"]
    ampl.param["InitialInventory"] = starting_inventory["Quantity"]

    def exercise(name, constraint, needs):
        if st.checkbox(f"Skip {name} exercise", value=True):
            ampl.eval(constraint)
        else:
            constraint = constraint[constraint.find("s.t.") :]
            constraint = constraint[: constraint.find("\n")] + "\n\t"
            answer = st.text_input(f"Implement the {name} below").strip()
            st.code(constraint + answer)
            help = f"Must use: {needs} and end with a ';'"
            forbidden = ["model", "data", "include", "shell", "cd"]
            validation_report = ""
            answer_nospace = answer.replace(" ", "")

            incomplete = False
            for s in needs:
                passed = s.replace(" ", "") in answer_nospace
                if not passed:
                    incomplete = True
                validation_report += f"- {'✅' if passed else '❌'} uses {s}\n"

            passed = answer_nospace.endswith(";")
            if not passed:
                incomplete = True

            validation_report += f"- {'✅' if passed else '❌'} ends with ';'\n"
            st.markdown(validation_report)

            if answer_nospace == "":
                st.error(f"Please write the equation above.")
            elif incomplete or any(s in answer_nospace for s in forbidden):
                st.error(f"Please complete the equation above.")
            else:
                output = ampl.get_output(constraint + answer + ";")
                if output != "":
                    output = re.sub(
                        r"\bfile\s*-\s*line\s+\d+\s+offset\s+\d+\b", "", output
                    )
                    st.error(f"❌ Syntax Error: {output}")
                else:
                    st.success("Great! No syntax errors!")

    solvers = ["gurobi", "xpress", "cplex", "mosek", "copt", "highs", "scip", "cbc"]
    solver = st.selectbox("Pick the MIP solver to use 👇", solvers, key="solver")
    if solver == "cplex":
        solver = "cplexmp"

    st.markdown("## Production Optimization Exercises")
    st.markdown("### Exercise 1: Demand Fulfillment Constraint")
    exercise(
        "Demand Fulfillment Constraint",
        demand_fulfillment,
        ["Demand[p, l, t]", "MetDemand[p, l, t]", "UnmetDemand[p, l, t]", "="],
    )

    st.markdown("### Exercise 2: Inventory Balance Constraint")
    exercise(
        "Inventory Balance Constraint",
        inventory_balance,
        [
            "StartingInventory[p, l, t]",
            "EndingInventory[p, l, prev(t)]",
            "InitialInventory[p, l]",
            "=",
        ],
    )

    st.markdown("### Exercise 3: Stock Balance Constraint")
    exercise(
        "Stock Balance Constraint",
        stock_balance,
        [
            "StartingInventory[p, l, t]",
            "Production[p, l, t]",
            "Demand[p, l, t]",
            "EndingInventory[p, l, t]",
            "=",
        ],
    )

    # Solve the problem
    output = ampl.solve(solver=solver, mp_options="outlev=1", return_output=True)
    st.markdown("### Solve output")
    st.write(f"```\n{output}\n```")

    # Demand report
    df = ampl.get_data("Demand", "MetDemand", "UnmetDemand").to_pandas()
    df.reset_index(inplace=True)
    df.columns = ["Product", "Location", "Period"] + list(df.columns[3:])

    def demand_report(df):
        columns = [
            "Demand",
            "MetDemand",
            "UnmetDemand",
        ]
        pivot_table = pd.pivot_table(
            df,
            index="Period",  # Use 'Period' as the index
            values=columns,  # Specify the columns to aggregate
            aggfunc="sum",  # Use sum as the aggregation function
        )[columns]
        st.dataframe(pivot_table.T)

    view = st.selectbox(
        "Demand Report",
        [
            "Pivot Table",
            "Pivot Table Per Product",
            "Pivot Table Per Location",
            "Full Table",
        ],
    )

    if view == "Pivot Table":
        demand_report(df)
    elif view == "Pivot Table Per Product":
        for product in instance.selected_products:
            st.markdown(f"Product: {product}")
            demand_report(df[df["Product"] == product])
    elif view == "Pivot Table Per Location":
        for location in instance.selected_locations:
            st.markdown(f"Location: {location}")
            demand_report(df[df["Location"] == location])
    else:
        st.dataframe(df, hide_index=True)

    # Material balance report
    df = ampl.get_data(
        "StartingInventory", "MetDemand", "Production", "EndingInventory"
    ).to_pandas()
    df.reset_index(inplace=True)
    df.columns = ["Product", "Location", "Period"] + list(df.columns[3:])

    view = st.selectbox(
        "Material Balance Report",
        [
            "Pivot Table",
            "Pivot Table Per Product",
            "Pivot Table Per Location",
            "Full Table",
        ],
    )

    def material_balance(df):
        columns = [
            "StartingInventory",
            "MetDemand",
            "Production",
            "EndingInventory",
        ]
        pivot_table = pd.pivot_table(
            df,
            index="Period",  # Use 'Period' as the index
            values=columns,  # Specify the columns to aggregate
            aggfunc="sum",  # Use sum as the aggregation function
        )[columns]
        st.dataframe(pivot_table.T)

    if view == "Pivot Table":
        material_balance(df)
    elif view == "Pivot Table Per Product":
        for product in instance.selected_products:
            st.markdown(f"Product: {product}")
            material_balance(df[df["Product"] == product])
    elif view == "Pivot Table Per Location":
        for location in instance.selected_locations:
            st.markdown(f"Location: {location}")
            material_balance(df[df["Location"] == location])
    else:
        st.dataframe(df, hide_index=True)
