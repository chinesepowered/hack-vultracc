import { Link } from "react-router";
import { CompassIcon } from "lucide-react";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-[1560px] px-4 sm:px-6 pt-10">
      <Card>
        <EmptyState
          icon={<CompassIcon />}
          title="Page not found"
          action={
            <Button asChild variant="outline">
              <Link to="/">Back to the September close</Link>
            </Button>
          }
        >
          This page does not exist. The close dashboard lists every client and run.
        </EmptyState>
      </Card>
    </div>
  );
}
