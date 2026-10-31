import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ApiClient } from "../../api/client";
import { SourcesCatalog } from "./SourcesCatalog";
it("lists registered sources and opens a selected source for editing", async () => {
 const choose = vi.fn();
 const client = { getSources: vi.fn().mockResolvedValue([{ source_id: "orders", kind: "http_json", revision: "r1", refresh_seconds: 60 }]) } as unknown as ApiClient;
 render(<SourcesCatalog client={client} reloadKey={0} onSelect={choose}/>);
 fireEvent.click(await screen.findByRole("button", { name: "Apri orders" }));
 expect(choose).toHaveBeenCalledWith("orders");
 expect(screen.getByText("HTTP JSON · ogni 60 s")).toBeInTheDocument();
});
